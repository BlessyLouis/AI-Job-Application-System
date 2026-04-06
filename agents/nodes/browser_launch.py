"""
agent/nodes/browser_launch.py
==============================
Node 3: Launch Playwright, navigate to job URL,
        detect ATS platform, and scrape the job description.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Optional

from agents.state import AgentState
from db.database import get_session
from db.models import ATSPlatform, Job, JobStatus


# ATS detection — URL patterns
ATS_URL_PATTERNS = [
    (re.compile(r"myworkday\.com|wd\d+\.myworkdayjobs\.com", re.I), ATSPlatform.WORKDAY),
    (re.compile(r"greenhouse\.io|boards\.greenhouse\.io",     re.I), ATSPlatform.GREENHOUSE),
    (re.compile(r"jobs\.lever\.co",                           re.I), ATSPlatform.LEVER),
    (re.compile(r"linkedin\.com/jobs",                        re.I), ATSPlatform.LINKEDIN),
]

# ATS detection — DOM fingerprints
ATS_DOM_FINGERPRINTS = [
    ('[data-automation-id="jobPostingHeader"]', ATSPlatform.WORKDAY),
    ('.greenhouse-job-board',                   ATSPlatform.GREENHOUSE),
    ('#greenhouse-app',                         ATSPlatform.GREENHOUSE),
    ('.lever-job-description',                  ATSPlatform.LEVER),
    ('.jobs-apply-button--top',                 ATSPlatform.LINKEDIN),
]


def _detect_ats_from_url(url: str) -> Optional[str]:
    for pattern, name in ATS_URL_PATTERNS:
        if pattern.search(url):
            return name
    return None


async def _detect_ats_from_dom(page) -> Optional[str]:
    for selector, name in ATS_DOM_FINGERPRINTS:
        try:
            el = await page.query_selector(selector)
            if el:
                return name
        except Exception:
            continue
    return None


async def _scrape_job_description(page) -> str:
    selectors = [
        ".job-description", "#job-description",
        '[data-automation-id="jobPostingDescription"]',
        ".posting-description", "#content",
        ".show-more-less-html__markup",
        "article", "main",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = await el.inner_text()
                if len(text) > 200:
                    return text[:8000]
        except Exception:
            continue
    try:
        return (await page.inner_text("body"))[:8000]
    except Exception:
        return ""


async def _browser_launch_async(state: AgentState) -> AgentState:
    from playwright.async_api import async_playwright

    url      = state["job_url"]
    headless = os.getenv("HEADLESS", "false").lower() == "true"

    print(f"[browser_launch] Opening {url} (headless={headless}) ...")

    playwright = await async_playwright().start()
    browser    = await playwright.chromium.launch(headless=headless)
    context    = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 900},
    )
    page = await context.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        print(f"[browser_launch] Navigation error: {e}")
        await browser.close()
        await playwright.stop()
        return {"error_message": str(e), "next_action": "failed"}

    # ATS detection
    ats = _detect_ats_from_url(url)
    if not ats:
        ats = await _detect_ats_from_dom(page)
    if not ats:
        ats = ATSPlatform.UNKNOWN
        print(f"[browser_launch] Could not detect ATS for {url}")
    else:
        print(f"[browser_launch] Detected ATS: {ats}")

    # Scrape JD
    jd = await _scrape_job_description(page)
    print(f"[browser_launch] Scraped {len(jd)} chars of JD text")

    # Title
    title = state.get("job_title") or ""
    if not title:
        try:
            title = await page.title()
            title = title.split("|")[0].split("–")[0].strip()
        except Exception:
            title = ""

    company = state.get("job_company") or ""

    # Persist to DB
    with get_session() as session:
        job = session.get(Job, state["job_id"])
        if job:
            job.ats_platform = ats
            if company: job.company = company
            if title:   job.title   = title
            session.commit()

    return {
        "page":            page,
        "ats_platform":    ats,
        "job_description": jd,
        "job_company":     company,
        "job_title":       title,
        "next_action":     "continue",
    }


def browser_launch_node(state: AgentState) -> AgentState:
    return asyncio.get_event_loop().run_until_complete(_browser_launch_async(state))

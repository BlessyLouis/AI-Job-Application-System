"""
agents/nodes/form_filler.py
============================
Key fixes:
- Dropdown fields: try Yes/No before free text for boolean questions
- Post-submit error detection
- More fields in skip/optional lists
- Better value normalization for dropdowns
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from agents.field_mapper import resolve_all_fields
from agents.state import AgentState
from db.database import get_session
from db.models import Job


# ---------------------------------------------------------------------------
# Skip lists
# ---------------------------------------------------------------------------

SKIP_LABELS = {
    "latitude", "longitude", "loc_group_id", "select...",
    "language dropdown menu", "invalid_location",
    "csrf", "token", "honeypot", "redirect", "utm", "source",
    # File inputs handled separately
    "resume", "attach", "cover letter", "cv",
    # Lever internal fields
    "urls[other]", "urls[twitter]", "urls[portfolio]",
    "additional information",
    # Amazon search UI (not part of application form)
    "country", "city", "region", "county",
}

SKIP_SUBSTRINGS = [
    "search for jobs", "search jobs", "language dropdown",
    "cards[", "type your response", "consent[", "eeo[race]",
]

# Fields that are optional — fill if we can but never trigger HITL
OPTIONAL_LABELS = {
    "publications", "google scholar", "ai policy",
    "why anthropic", "why figma", "why do you want",
    "optional", "personal preferences", "additional info",
    "hispanic", "latino", "race", "ethnicity",
}


def _is_skip(label: str) -> bool:
    l = label.lower().strip()
    if l in SKIP_LABELS:
        return True
    if any(s in l for s in SKIP_SUBSTRINGS):
        return True
    return False


def _is_optional(label: str) -> bool:
    l = label.lower()
    return any(o in l for o in OPTIONAL_LABELS)


# ---------------------------------------------------------------------------
# Value normalization for dropdowns
# ---------------------------------------------------------------------------

def _normalize_for_dropdown(value: str) -> List[str]:
    """
    Return a list of candidate values to try when selecting from a dropdown.
    Order matters — try most specific first.
    """
    v = value.strip()
    v_lower = v.lower()

    candidates = [v]  # always try the raw value first

    # Boolean normalization
    if v_lower in ("yes", "true", "1"):
        candidates = ["Yes", "yes", "YES", "Y", v]
    elif v_lower in ("no", "false", "0"):
        candidates = ["No", "no", "NO", "N", v]

    # Veteran status
    elif "not a veteran" in v_lower or "not veteran" in v_lower:
        candidates = [
            "I am not a protected veteran",
            "Not a Protected Veteran",
            "I am not a veteran",
            "Not a veteran",
            "No",
            v,
        ]

    # Disability
    elif "no disability" in v_lower:
        candidates = [
            "I don't have a disability",
            "No disability",
            "I do not have a disability",
            "No",
            v,
        ]

    # Gender
    elif v_lower == "male":
        candidates = ["Male", "Man", "M", v]
    elif v_lower == "female":
        candidates = ["Female", "Woman", "F", v]

    # Decline / prefer not
    elif "decline" in v_lower or "prefer not" in v_lower:
        candidates = [
            "Decline to state",
            "Prefer not to say",
            "Prefer not to answer",
            "I prefer not to answer",
            "Decline to Self Identify",
            v,
        ]

    # India / country
    elif v_lower == "india":
        candidates = ["India", "IN", v]

    return candidates


# ---------------------------------------------------------------------------
# Field discovery
# ---------------------------------------------------------------------------

async def _discover_form_fields(page) -> List[Dict[str, Any]]:
    fields = await page.evaluate("""() => {
        const results = [];
        const seen = new Set();

        document.querySelectorAll(
            'input:not([type=hidden]):not([type=submit]):not([type=button])' +
            ':not([type=image]):not([type=file]),' +
            'textarea, select'
        ).forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return;

            let label = '';
            if (el.id) {
                const lbl = document.querySelector(`label[for="${el.id}"]`);
                if (lbl) label = lbl.innerText.trim().replace(/\\*/g, '').trim();
            }
            if (!label) label = el.getAttribute('aria-label') || '';
            if (!label) label = el.getAttribute('placeholder') || '';
            if (!label) label = el.getAttribute('name') || '';
            if (!label) {
                const parent = el.closest('label');
                if (parent) label = parent.childNodes[0]?.textContent?.trim() || '';
            }
            if (!label && el.previousElementSibling) {
                label = el.previousElementSibling.innerText?.trim() || '';
            }

            label = label.replace(/\\*/g, '').trim();
            if (!label || label.length > 300) return;

            let selector = '';
            if (el.id)        selector = '#' + el.id;
            else if (el.name) selector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
            else              selector = el.tagName.toLowerCase() +
                                         '[placeholder="' + (el.getAttribute('placeholder') || '') + '"]';

            if (seen.has(selector)) return;
            seen.add(selector);

            // Get available options for select elements
            let options = [];
            if (el.tagName === 'SELECT') {
                options = Array.from(el.options).map(o => o.text.trim()).filter(t => t);
            }

            results.push({ label, type: el.type || el.tagName.toLowerCase(),
                           selector, tagName: el.tagName.toLowerCase(), options });
        });
        return results;
    }""")

    clean = [f for f in (fields or []) if not _is_skip(f.get("label", ""))]
    return clean


# ---------------------------------------------------------------------------
# Resume upload
# ---------------------------------------------------------------------------

async def _upload_resume(page, resume_path: str) -> bool:
    if not resume_path or not os.path.exists(resume_path):
        print(f"[form_filler] Resume not found: {resume_path}")
        return False

    for sel in ['input[type=file]', 'input[name=resume]', 'input[name=file]', '#resume']:
        try:
            el = await page.query_selector(sel)
            if el:
                await page.set_input_files(sel, resume_path)
                print(f"[form_filler] Uploaded resume via {sel}")
                await page.wait_for_timeout(1000)
                return True
        except Exception:
            continue

    try:
        async with page.expect_file_chooser(timeout=3000) as fc_info:
            btn = await page.query_selector(
                'button:has-text("Upload"), button:has-text("Attach"), '
                'label:has-text("Upload"), label:has-text("Resume")'
            )
            if btn:
                await btn.click()
        fc = await fc_info.value
        await fc.set_files(resume_path)
        print("[form_filler] Uploaded resume via file chooser")
        await page.wait_for_timeout(1000)
        return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Field filling
# ---------------------------------------------------------------------------

async def _fill_select(locator, value: str, options: List[str]) -> bool:
    """Try multiple candidate values for a select dropdown."""
    candidates = _normalize_for_dropdown(value)

    # Also try matching against actual available options
    if options:
        v_lower = value.lower()
        for opt in options:
            opt_lower = opt.lower()
            # Exact or partial match
            if v_lower in opt_lower or opt_lower in v_lower:
                if opt not in candidates:
                    candidates.insert(0, opt)

    for candidate in candidates:
        try:
            await locator.select_option(label=candidate, timeout=2000)
            return True
        except Exception:
            pass
        try:
            await locator.select_option(value=candidate, timeout=2000)
            return True
        except Exception:
            pass

    return False


async def _fill_field(page, field: Dict, value: str) -> bool:
    selector = field["selector"]
    tag      = field.get("tagName", "input")
    ftype    = field.get("type", "text")
    options  = field.get("options", [])

    try:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=3000)
        except Exception:
            return False

        if tag == "select":
            ok = await _fill_select(locator, value, options)
            if not ok:
                print(f"[form_filler] Select failed for '{field['label']}' "
                      f"(tried: {_normalize_for_dropdown(value)[:3]}, available: {options[:5]})")
            return ok

        elif ftype in ("checkbox", "radio"):
            if value.lower() in ("yes", "true", "1"):
                await locator.check(timeout=3000)
            return True

        elif tag == "textarea" or ftype in ("text", "email", "tel", "number", "url", "search", ""):
            await locator.fill("", timeout=3000)
            await locator.type(value, delay=15)
            return True

        else:
            await locator.fill(value, timeout=3000)
            return True

    except Exception as e:
        short = str(e).split("\n")[0][:100]
        print(f"[form_filler] Could not fill '{field['label']}': {short}")
        return False


# ---------------------------------------------------------------------------
# Post-submit error detection
# ---------------------------------------------------------------------------

async def _check_for_errors(page) -> List[str]:
    """Detect validation errors on the page after submission attempt."""
    try:
        errors = await page.evaluate("""() => {
            const errorSelectors = [
                '.error', '.field-error', '.validation-error',
                '[class*=error]', '[class*=invalid]',
                '.alert-danger', '.form-error',
                '[aria-invalid=true]',
            ];
            const messages = [];
            for (const sel of errorSelectors) {
                document.querySelectorAll(sel).forEach(el => {
                    const text = el.innerText?.trim();
                    if (text && text.length < 200 && text.length > 2) {
                        messages.push(text);
                    }
                });
            }
            return [...new Set(messages)].slice(0, 10);
        }""")
        return errors or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# ATS navigation
# ---------------------------------------------------------------------------

async def _navigate_to_lever_apply(page) -> None:
    if "/apply" not in page.url:
        apply_url = page.url.split("?")[0].rstrip("/") + "/apply"
        try:
            await page.goto(apply_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            print(f"[form_filler] Navigated to Lever apply: {apply_url}")
        except Exception as e:
            print(f"[form_filler] Lever /apply nav failed: {e}")


async def _navigate_to_workday_apply(page) -> None:
    selectors = [
        '[data-automation-id="Apply"]',
        'a:has-text("Apply for this job")',
        'button:has-text("Apply")',
    ]
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)
                await page.wait_for_timeout(2000)
                print("[form_filler] Clicked Workday Apply")
                return
        except Exception:
            continue
    await page.wait_for_timeout(3000)


async def _navigate_to_greenhouse_apply(page) -> None:
    try:
        btn = await page.query_selector(
            'a#apply_button, a:has-text("Apply for this Job"), button:has-text("Apply")'
        )
        if btn and await btn.is_visible():
            await btn.click()
            await page.wait_for_timeout(2000)
            print("[form_filler] Clicked Greenhouse Apply button")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def _form_filler_async(state: AgentState) -> AgentState:
    page        = state["page"]
    ats         = state.get("ats_platform", "unknown")
    profile     = state["candidate_profile"]
    customs     = state.get("custom_answers", {})
    jd          = state.get("job_description", "")
    company     = state.get("job_company", "")
    title       = state.get("job_title", "")
    resume_path = state.get("tailored_resume_path") or profile.get("resume_path", "")

    # Navigate to form
    if ats == "lever":
        await _navigate_to_lever_apply(page)
    elif ats == "workday":
        await _navigate_to_workday_apply(page)
    elif ats == "greenhouse":
        await _navigate_to_greenhouse_apply(page)

    # Upload resume
    if resume_path:
        await _upload_resume(page, resume_path)

    # Discover fields
    print("[form_filler] Discovering form fields ...")
    form_fields = await _discover_form_fields(page)
    print(f"[form_filler] Found {len(form_fields)} field(s) after filtering")

    if not form_fields:
        return {"form_fields": [], "filled_fields": {}, "unanswered_fields": [], "next_action": "submit"}

    # Resolve all values
    filled_map, hitl_labels, _ = resolve_all_fields(form_fields, profile, customs, jd, company, title)

    # Fill fields
    successfully_filled: Dict[str, str] = {}
    for field in form_fields:
        label = field.get("label", "")
        if not label or label not in filled_map:
            continue
        value = filled_map[label]
        ok = await _fill_field(page, field, value)
        if ok:
            successfully_filled[label] = value
            print(f"[form_filler] OK  '{label}' -> '{value[:60]}'")
        else:
            if label not in hitl_labels:
                hitl_labels.append(label)

    # Separate required vs optional
    required_hitl = [l for l in hitl_labels if not _is_optional(l)]
    optional_skip = [l for l in hitl_labels if _is_optional(l)]

    if optional_skip:
        print(f"[form_filler] Skipping {len(optional_skip)} optional fields: {optional_skip}")

    if required_hitl:
        with get_session() as session:
            job = session.get(Job, state["job_id"])
            if job:
                job.unanswered_fields = required_hitl
                session.commit()

    next_action = "hitl" if required_hitl else "submit"
    print(f"[form_filler] Filled {len(successfully_filled)}, "
          f"HITL needed: {len(required_hitl)}, optional skipped: {len(optional_skip)}")

    return {
        "form_fields":       form_fields,
        "filled_fields":     successfully_filled,
        "unanswered_fields": required_hitl,
        "next_action":       next_action,
        "page":              page,
    }


def form_filler_node(state: AgentState) -> AgentState:
    return asyncio.get_event_loop().run_until_complete(_form_filler_async(state))

"""
agents/nodes/hitl.py + submitter_node
======================================
- Empty Enter = skip that field
- Full timeout = backlog
- Submitter now checks for form validation errors after clicking submit
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from typing import Dict, List

from agents.state import AgentState
from db.database import get_session
from db.models import CustomAnswer, Job, JobStatus


HITL_TIMEOUT_SECONDS = 30


async def _prompt_with_timeout(question: str, timeout: int):
    print(f"\n{'='*60}")
    print(f"AGENT NEEDS YOUR INPUT")
    print(f"{'='*60}")
    print(f"Field  : {question}")
    print(f"Timeout: {timeout}s  |  Press Enter to SKIP this field")
    print(f"         Type your answer and press Enter to fill it")
    print(f"{'='*60}")

    for remaining in range(timeout, 0, -1):
        sys.stdout.write(f"\r  {remaining:2d}s  Answer: ")
        sys.stdout.flush()
        try:
            answer = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline),
                timeout=1.0,
            )
            sys.stdout.write("\n")
            return answer.strip()
        except asyncio.TimeoutError:
            continue

    sys.stdout.write("\n  Timed out — moving to backlog.\n")
    return None


async def _hitl_async(state: AgentState) -> AgentState:
    unanswered   = state.get("unanswered_fields", [])
    form_fields  = state.get("form_fields", [])
    page         = state.get("page")
    filled       = dict(state.get("filled_fields", {}))
    candidate_id = state["candidate_id"]
    job_id       = state["job_id"]
    still_unanswered: List[str] = []

    for label in unanswered:
        answer = await _prompt_with_timeout(label, HITL_TIMEOUT_SECONDS)

        if answer is None:
            print(f"[hitl] Timeout — backlogging job {job_id}")
            remaining = [l for l in unanswered if l not in filled]
            with get_session() as session:
                job = session.get(Job, job_id)
                if job:
                    job.unanswered_fields = remaining
                    job.status = JobStatus.BACKLOG
                    session.commit()
            return {"unanswered_fields": remaining, "filled_fields": filled, "next_action": "backlog"}

        if answer == "":
            print(f"[hitl] Skipped '{label}'")
            still_unanswered.append(label)
            continue

        from agents.field_mapper import _normalise_key
        key = _normalise_key(label)
        with get_session() as session:
            existing = session.query(CustomAnswer).filter_by(
                candidate_id=candidate_id, key=key).first()
            if existing:
                existing.value = answer
            else:
                session.add(CustomAnswer(candidate_id=candidate_id, key=key,
                                         value=answer, notes=f"HITL: {label}"))
            session.commit()

        if page:
            for field in [f for f in form_fields if f.get("label") == label]:
                try:
                    loc = page.locator(field["selector"]).first
                    await loc.fill("", timeout=3000)
                    await loc.type(answer, delay=15)
                except Exception as e:
                    print(f"[hitl] Browser fill failed for '{label}': {e}")

        filled[label] = answer
        print(f"[hitl] Filled '{label}' -> '{answer[:50]}'")

    return {"filled_fields": filled, "unanswered_fields": still_unanswered, "next_action": "submit"}


def hitl_node(state: AgentState) -> AgentState:
    return asyncio.get_event_loop().run_until_complete(_hitl_async(state))


# ---------------------------------------------------------------------------
# Submitter — with form error detection
# ---------------------------------------------------------------------------

async def _check_submission_success(page) -> tuple[bool, List[str]]:
    """Returns (success, error_messages)."""
    await page.wait_for_timeout(2000)

    # Check for success indicators
    try:
        success_sel = (
            '.confirmation, #confirmation, '
            'h1:has-text("Thank"), h1:has-text("Application received"), '
            'h2:has-text("Thanks"), h2:has-text("submitted"), '
            '.success-message, [class*=confirmation]'
        )
        el = await page.query_selector(success_sel)
        if el:
            return True, []
    except Exception:
        pass

    # Check for validation errors
    try:
        errors = await page.evaluate("""() => {
            const sels = [
                '.error-message', '.field-error', '.validation-error',
                '.alert-danger', '[class*="error"]:not(script)',
                '[aria-invalid="true"]', '.invalid-feedback',
                'span.error', 'p.error', 'div.error',
            ];
            const msgs = new Set();
            sels.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    const t = el.innerText?.trim();
                    if (t && t.length > 2 && t.length < 300) msgs.add(t);
                });
            });
            return [...msgs].slice(0, 10);
        }""")
        if errors:
            return False, errors
    except Exception:
        pass

    # No clear success or error — assume submitted (may be a redirect)
    return True, []


async def _submitter_async(state: AgentState) -> AgentState:
    page       = state.get("page")
    job_id     = state["job_id"]
    ats        = state.get("ats_platform", "unknown")
    unanswered = state.get("unanswered_fields", [])

    if not page:
        return {"status": "failed", "error_message": "No browser page"}

    SUBMIT_SELECTORS = {
        "workday":    ['[data-automation-id="bottom-navigation-next-button"]',
                       '[data-automation-id="submit"]', 'button:has-text("Submit")'],
        "greenhouse": ['#submit_app', 'button[type=submit]', 'input[type=submit]'],
        "lever":      ['.template-btn-submit', 'button[type=submit]',
                       'button:has-text("Submit Application")'],
        "unknown":    ['button[type=submit]', 'input[type=submit]',
                       'button:has-text("Submit")', 'button:has-text("Apply")'],
    }

    selectors = SUBMIT_SELECTORS.get(ats, SUBMIT_SELECTORS["unknown"])
    clicked   = False

    for sel in selectors:
        try:
            locator = page.locator(sel).first
            if await locator.is_visible(timeout=3000):
                await locator.click(timeout=5000)
                clicked = True
                print(f"[submitter] Clicked: {sel}")
                break
        except Exception as e:
            print(f"[submitter] '{sel}' failed: {str(e).split(chr(10))[0][:60]}")

    if not clicked:
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.failure_reason = "Submit button not found"
                session.commit()
        return {"status": "failed", "error_message": "Submit button not found"}

    # Check if submission succeeded or had errors
    success, errors = await _check_submission_success(page)

    if not success and errors:
        print(f"[submitter] Form validation errors detected: {errors}")
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.failure_reason = f"Form errors: {'; '.join(errors[:3])}"
                session.commit()
        return {"status": "failed", "error_message": f"Form errors: {errors}"}

    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status            = JobStatus.SUBMITTED
            job.submitted_at      = datetime.utcnow()
            job.unanswered_fields = unanswered
            session.commit()

    print(f"[submitter] Job {job_id} submitted successfully!")

    try:
        await page.close()
    except Exception:
        pass

    return {"status": "submitted"}


def submitter_node(state: AgentState) -> AgentState:
    return asyncio.get_event_loop().run_until_complete(_submitter_async(state))

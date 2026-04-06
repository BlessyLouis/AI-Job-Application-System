"""
ats/workday.py
==============
Workday ATS handler.

Workday is the most complex ATS — it uses a custom React-based UI
with non-standard elements, multi-step wizard forms, and heavy
JavaScript rendering. All selectors use Workday's data-automation-id
attributes which are stable across tenants.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ats.base import ATSHandler


class WorkdayHandler(ATSHandler):

    platform_name = "workday"

    # ── Stable Workday automation selectors ──────────────────────────────────
    # These data-automation-id values are consistent across all Workday tenants

    SEL_SIGN_IN_BTN     = '[data-automation-id="signInButton"]'
    SEL_EMAIL_INPUT     = '[data-automation-id="email"]'
    SEL_PASSWORD_INPUT  = '[data-automation-id="password"]'
    SEL_SUBMIT_LOGIN    = '[data-automation-id="click_filter"]'

    SEL_APPLY_BTN       = '[data-automation-id="Apply"]'
    SEL_APPLY_MANUALLY  = '[data-automation-id="applyManually"]'   # when resume parsing is offered

    SEL_NEXT_BTN        = '[data-automation-id="bottom-navigation-next-button"]'
    SEL_SAVE_BTN        = '[data-automation-id="bottom-navigation-save-button"]'
    SEL_SUBMIT_BTN      = '[data-automation-id="bottom-navigation-next-button"]'   # last step

    SEL_RESUME_UPLOAD   = 'input[data-automation-id="file-upload-input-ref"]'
    SEL_FORM_SECTION    = '[data-automation-id="formSection"]'

    # ── Auth ─────────────────────────────────────────────────────────────────

    async def sign_in(self) -> bool:
        email    = self.credentials.get("WORKDAY_EMAIL",    "")
        password = self.credentials.get("WORKDAY_PASSWORD", "")

        if not email or not password:
            print("[workday] No credentials — proceeding as guest (may fail later)")
            return True

        # Click "Sign In" if the button exists on the page
        if await self.element_exists(self.SEL_SIGN_IN_BTN):
            await self.safe_click(self.SEL_SIGN_IN_BTN)
            await self.page.wait_for_timeout(1500)

        # Fill credentials
        filled = await self.safe_fill(self.SEL_EMAIL_INPUT,    email)
        filled = filled and await self.safe_fill(self.SEL_PASSWORD_INPUT, password)

        if not filled:
            print("[workday] Could not find login fields")
            return False

        await self.safe_click(self.SEL_SUBMIT_LOGIN)
        await self.wait_for_navigation()

        # Check for error message
        if await self.element_exists('[data-automation-id="errorMessage"]', timeout=2000):
            print("[workday] ❌ Login failed — check WORKDAY_EMAIL / WORKDAY_PASSWORD in .env")
            return False

        print("[workday] ✅ Signed in")
        return True

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate_to_application(self) -> bool:
        """Click the Apply button, skip resume parsing if offered."""
        # Primary Apply button
        if not await self.safe_click(self.SEL_APPLY_BTN):
            print("[workday] Could not find Apply button")
            return False

        await self.wait_for_navigation()

        # Workday often offers to auto-fill from resume — skip it, apply manually
        if await self.element_exists(self.SEL_APPLY_MANUALLY, timeout=3000):
            await self.safe_click(self.SEL_APPLY_MANUALLY)
            await self.wait_for_navigation()

        # Handle "My Experience" intro page if present
        if await self.element_exists('[data-automation-id="myExperienceIntro"]', timeout=2000):
            await self.safe_click(self.SEL_NEXT_BTN)
            await self.wait_for_navigation()

        print("[workday] ✅ On application form")
        return True

    # ── Form field discovery ──────────────────────────────────────────────────

    async def get_form_fields(self) -> List[Dict[str, Any]]:
        """
        Workday forms use data-automation-id on labels and inputs.
        We query all visible form inputs and pair them with their labels.
        """
        fields = await self.page.evaluate("""() => {
            const results = [];

            // Text inputs
            document.querySelectorAll('[data-automation-id] input, [data-automation-id] textarea').forEach(el => {
                if (el.type === 'hidden' || el.type === 'submit') return;

                let label = '';
                // Workday wraps inputs in a div with a label sibling
                const container = el.closest('[data-automation-id]');
                if (container) {
                    const lbl = container.querySelector('label') || container.previousElementSibling;
                    if (lbl) label = lbl.innerText?.trim() || '';
                }
                if (!label) label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
                if (!label) return;

                const automationId = container?.getAttribute('data-automation-id') || '';
                results.push({
                    label:        label,
                    type:         el.type || el.tagName.toLowerCase(),
                    selector:     automationId
                        ? `[data-automation-id="${automationId}"] input`
                        : (el.id ? `#${el.id}` : `input[placeholder="${el.placeholder}"]`),
                    automationId: automationId,
                    tagName:      el.tagName.toLowerCase(),
                });
            });

            // Select / dropdown (Workday uses custom listboxes)
            document.querySelectorAll('[role="combobox"], [role="listbox"]').forEach(el => {
                const label = el.getAttribute('aria-label') || el.closest('label')?.innerText?.trim() || '';
                if (!label) return;
                results.push({
                    label:    label,
                    type:     'select',
                    selector: `[aria-label="${label}"]`,
                    tagName:  'select',
                });
            });

            return results;
        }""")
        return fields or []

    # ── Filling ───────────────────────────────────────────────────────────────

    async def fill_text_field(self, selector: str, value: str) -> bool:
        return await self.safe_fill(selector, value)

    async def fill_select_field(self, selector: str, value: str) -> bool:
        """
        Workday dropdowns are custom (not native <select>).
        Strategy: click the combobox → type to filter → click the matching option.
        """
        try:
            # Click to open the dropdown
            el = await self.page.wait_for_selector(selector, timeout=5000, state="visible")
            if not el:
                return False
            await el.click()
            await self.page.wait_for_timeout(500)

            # Type to filter options
            await el.type(value[:20], delay=50)
            await self.page.wait_for_timeout(800)

            # Click first matching option in the dropdown list
            option_sel = f'[role="option"]:has-text("{value[:30]}")'
            if await self.element_exists(option_sel, timeout=3000):
                await self.safe_click(option_sel)
                return True

            # Fallback: press Enter to accept whatever is highlighted
            await el.press("Enter")
            return True

        except Exception as e:
            print(f"[workday] fill_select_field failed for {selector!r}: {e}")
            return False

    # ── Multi-step navigation ─────────────────────────────────────────────────

    async def next_step(self) -> bool:
        """Click the Next button to advance to the next form step."""
        if await self.safe_click(self.SEL_NEXT_BTN):
            await self.wait_for_navigation()
            return True
        return False

    async def upload_resume(self, resume_path: str) -> bool:
        """Upload resume PDF to Workday's file upload input."""
        if not resume_path or not os.path.exists(resume_path):
            print(f"[workday] Resume file not found: {resume_path}")
            return False
        return await self.fill_file_field(self.SEL_RESUME_UPLOAD, resume_path)

    # ── Submit ────────────────────────────────────────────────────────────────

    async def submit(self) -> bool:
        """
        Workday's submit is the 'Next' button on the final review step.
        We look for a 'Submit' label specifically.
        """
        submit_selectors = [
            '[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")',
            '[data-automation-id="submit"]',
            'button:has-text("Submit Application")',
            self.SEL_NEXT_BTN,  # fallback — might be the last step's next
        ]
        for sel in submit_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await self.wait_for_navigation()
                    print("[workday] ✅ Submitted")
                    return True
            except Exception:
                continue
        print("[workday] ❌ Submit button not found")
        return False

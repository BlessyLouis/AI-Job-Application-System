"""
ats/greenhouse.py
=================
Greenhouse ATS handler.

Greenhouse uses standard HTML forms — the simplest ATS to automate.
The application form is a single page (no wizard) with native
<input>, <select>, and <textarea> elements.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ats.base import ATSHandler


class GreenhouseHandler(ATSHandler):

    platform_name = "greenhouse"

    # Greenhouse doesn't require an account to apply — just a form submission
    # Selectors are stable across all Greenhouse-hosted job boards

    SEL_APPLY_BTN    = '#apply_button, .apply-button, a[href*="apply"]'
    SEL_SUBMIT_BTN   = '#submit_app, input[type="submit"], button[type="submit"]'
    SEL_RESUME_INPUT = 'input#resume, input[name="resume"], input[type="file"]'

    # ── Auth (Greenhouse usually doesn't require login) ───────────────────────

    async def sign_in(self) -> bool:
        # Most Greenhouse boards are public — no login needed
        print("[greenhouse] No sign-in required (public board)")
        return True

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate_to_application(self) -> bool:
        """
        Greenhouse job postings have an 'Apply for this Job' button that
        either scrolls to a form on the same page or navigates to /apply.
        """
        if await self.element_exists(self.SEL_APPLY_BTN, timeout=5000):
            await self.safe_click(self.SEL_APPLY_BTN)
            await self.page.wait_for_timeout(1500)

        # The form should now be visible
        if await self.element_exists('#application_form, form#application, .application-form', timeout=5000):
            print("[greenhouse] ✅ Application form is visible")
            return True

        # May have navigated to a new URL — wait for form
        try:
            await self.page.wait_for_selector('input[type="submit"], button[type="submit"]', timeout=8000)
            print("[greenhouse] ✅ On application form page")
            return True
        except Exception:
            print("[greenhouse] ⚠ Could not confirm application form — proceeding anyway")
            return True  # Try to proceed; form_filler will discover what's there

    # ── Form field discovery ──────────────────────────────────────────────────

    async def get_form_fields(self) -> List[Dict[str, Any]]:
        """
        Greenhouse forms use standard HTML with <label for="id"> associations.
        Very straightforward to scrape.
        """
        fields = await self.page.evaluate("""() => {
            const results = [];

            document.querySelectorAll('input:not([type=hidden]):not([type=submit]), textarea, select').forEach(el => {
                let label = '';

                // Standard label[for] association
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim().replace('*', '').trim();
                }

                // aria-label fallback
                if (!label) label = el.getAttribute('aria-label') || '';

                // placeholder fallback
                if (!label) label = el.getAttribute('placeholder') || '';

                if (!label || label.length > 300) return;

                let selector = el.tagName.toLowerCase();
                if (el.id)          selector = `#${el.id}`;
                else if (el.name)   selector = `[name="${el.name}"]`;

                results.push({
                    label:   label,
                    type:    el.type || el.tagName.toLowerCase(),
                    selector: selector,
                    tagName:  el.tagName.toLowerCase(),
                });
            });

            return results;
        }""")
        return fields or []

    # ── Filling ───────────────────────────────────────────────────────────────

    async def fill_text_field(self, selector: str, value: str) -> bool:
        return await self.safe_fill(selector, value)

    async def fill_select_field(self, selector: str, value: str) -> bool:
        """Greenhouse uses native <select> elements — straightforward."""
        try:
            await self.page.select_option(selector, label=value)
            return True
        except Exception:
            try:
                # Try selecting by value text (partial match)
                options = await self.page.eval_on_selector_all(
                    f"{selector} option",
                    "els => els.map(e => ({value: e.value, text: e.innerText}))"
                )
                for opt in options:
                    if value.lower() in opt["text"].lower():
                        await self.page.select_option(selector, value=opt["value"])
                        return True
            except Exception as e:
                print(f"[greenhouse] fill_select_field failed for {selector!r}: {e}")
        return False

    async def upload_resume(self, resume_path: str) -> bool:
        if not resume_path or not os.path.exists(resume_path):
            return False
        return await self.fill_file_field(self.SEL_RESUME_INPUT, resume_path)

    # ── Submit ────────────────────────────────────────────────────────────────

    async def submit(self) -> bool:
        selectors = [
            '#submit_app',
            'input[type="submit"]',
            'button[type="submit"]',
            'button:has-text("Submit Application")',
            'button:has-text("Apply")',
        ]
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await self.wait_for_navigation()
                    # Check for confirmation
                    if await self.element_exists('.confirmation, #confirmation, h1:has-text("Application")', timeout=5000):
                        print("[greenhouse] ✅ Submitted — confirmation page detected")
                    else:
                        print("[greenhouse] ✅ Submit clicked (no confirmation page found)")
                    return True
            except Exception:
                continue
        print("[greenhouse] ❌ Submit button not found")
        return False

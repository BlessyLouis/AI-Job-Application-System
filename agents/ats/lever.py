"""
ats/lever.py
============
Lever ATS handler.

Lever job boards (jobs.lever.co) have a clean, consistent structure.
Application forms are single-page with standard inputs, plus a resume
upload and optional cover letter field.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ats.base import ATSHandler


class LeverHandler(ATSHandler):

    platform_name = "lever"

    SEL_APPLY_BTN    = '.template-btn-submit, a[href*="/apply"], button:has-text("Apply")'
    SEL_SUBMIT_BTN   = '.template-btn-submit[type="submit"], button[type="submit"]'
    SEL_RESUME_INPUT = 'input[name="resume"], input[type="file"]'
    SEL_CL_TEXTAREA  = 'textarea[name="comments"], textarea[placeholder*="cover"], #additional-information'

    # ── Auth (Lever boards are public) ────────────────────────────────────────

    async def sign_in(self) -> bool:
        print("[lever] No sign-in required (public board)")
        return True

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate_to_application(self) -> bool:
        """
        Lever posting pages have an 'Apply' button that navigates to /apply suffix URL.
        e.g. https://jobs.lever.co/company/job-id/apply
        """
        current_url = self.page.url

        # If already on /apply page, skip navigation
        if "/apply" in current_url:
            print("[lever] ✅ Already on application page")
            return True

        # Click the Apply button
        if await self.safe_click(self.SEL_APPLY_BTN):
            await self.wait_for_navigation()
            print("[lever] ✅ Navigated to application form")
            return True

        # Try direct URL append
        apply_url = current_url.rstrip("/") + "/apply"
        try:
            await self.page.goto(apply_url, wait_until="domcontentloaded", timeout=15000)
            await self.page.wait_for_timeout(1000)
            print(f"[lever] ✅ Navigated directly to {apply_url}")
            return True
        except Exception as e:
            print(f"[lever] Navigation failed: {e}")
            return False

    # ── Form field discovery ──────────────────────────────────────────────────

    async def get_form_fields(self) -> List[Dict[str, Any]]:
        """
        Lever's /apply page uses a consistent form structure with
        <label> wrapping inputs or label[for] associations.
        """
        fields = await self.page.evaluate("""() => {
            const results = [];

            document.querySelectorAll(
                '.application-form input:not([type=hidden]):not([type=submit]),' +
                '.application-form textarea,' +
                '.application-form select,' +
                'form input:not([type=hidden]):not([type=submit]),' +
                'form textarea,' +
                'form select'
            ).forEach(el => {
                let label = '';

                // label wrapping the input
                const parentLabel = el.closest('label');
                if (parentLabel) {
                    label = parentLabel.childNodes[0]?.textContent?.trim() || '';
                }

                // label[for] association
                if (!label && el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim();
                }

                // data-field-id (Lever sometimes uses this)
                if (!label) label = el.getAttribute('data-field-id') || '';
                if (!label) label = el.getAttribute('aria-label') || '';
                if (!label) label = el.getAttribute('placeholder') || '';
                if (!label) label = el.getAttribute('name') || '';

                if (!label || label.length > 300) return;

                // Clean up asterisks / "(required)" from labels
                label = label.replace(/\*|\(required\)/gi, '').trim();

                let selector = '';
                if (el.id)        selector = `#${el.id}`;
                else if (el.name) selector = `[name="${el.name}"]`;
                else              selector = `${el.tagName.toLowerCase()}[placeholder="${el.placeholder || ''}"]`;

                results.push({
                    label,
                    type:    el.type || el.tagName.toLowerCase(),
                    selector,
                    tagName: el.tagName.toLowerCase(),
                });
            });

            return results;
        }""")
        return fields or []

    # ── Filling ───────────────────────────────────────────────────────────────

    async def fill_text_field(self, selector: str, value: str) -> bool:
        return await self.safe_fill(selector, value)

    async def fill_select_field(self, selector: str, value: str) -> bool:
        """Lever uses native <select> with standard options."""
        try:
            await self.page.select_option(selector, label=value)
            return True
        except Exception:
            try:
                await self.page.select_option(selector, value=value)
                return True
            except Exception as e:
                print(f"[lever] fill_select_field failed for {selector!r}: {e}")
        return False

    async def fill_cover_letter(self, cover_letter_text: str) -> bool:
        """Fill the optional cover letter / additional info textarea."""
        if not cover_letter_text:
            return True
        try:
            el = await self.page.query_selector(self.SEL_CL_TEXTAREA)
            if el and await el.is_visible():
                await el.triple_click()
                await el.type(cover_letter_text[:3000], delay=10)  # Lever has char limits
                print("[lever] ✅ Cover letter filled")
                return True
        except Exception as e:
            print(f"[lever] Could not fill cover letter: {e}")
        return False

    async def upload_resume(self, resume_path: str) -> bool:
        if not resume_path or not os.path.exists(resume_path):
            return False
        return await self.fill_file_field(self.SEL_RESUME_INPUT, resume_path)

    # ── Submit ────────────────────────────────────────────────────────────────

    async def submit(self) -> bool:
        selectors = [
            '.template-btn-submit',
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit Application")',
            'button:has-text("Apply")',
        ]
        for sel in selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await self.wait_for_navigation()

                    # Lever shows a "Thanks for applying" confirmation
                    if await self.element_exists(
                        '.application-confirmation, h2:has-text("Thanks"), h1:has-text("Application received")',
                        timeout=6000
                    ):
                        print("[lever] ✅ Submitted — confirmation received")
                    else:
                        print("[lever] ✅ Submit clicked")
                    return True
            except Exception:
                continue
        print("[lever] ❌ Submit button not found")
        return False

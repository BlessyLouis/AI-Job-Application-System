"""
ats/base.py
===========
Abstract base class for all ATS platform handlers.

Every supported ATS (Workday, Greenhouse, Lever, LinkedIn) implements
this interface. The form_filler node calls these methods instead of
interacting with the browser directly — keeping platform-specific logic
cleanly isolated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ATSHandler(ABC):
    """
    Abstract interface for an ATS platform.

    Each subclass knows how to:
      1. Detect itself from a URL / DOM
      2. Sign in with candidate credentials
      3. Navigate to the application form
      4. Enumerate form fields
      5. Fill individual fields (text, select, file upload)
      6. Submit the form
    """

    def __init__(self, page, credentials: Dict[str, str]):
        """
        Args:
            page:        Playwright async Page object (already navigated to the job URL)
            credentials: Dict with keys like "email", "password" from .env
        """
        self.page        = page
        self.credentials = credentials

    # ── Identity ─────────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable name, e.g. 'workday'."""
        ...

    # ── Auth ─────────────────────────────────────────────────────────────────

    @abstractmethod
    async def sign_in(self) -> bool:
        """
        Sign in to the ATS with the candidate's credentials.
        Returns True on success, False if login failed.
        """
        ...

    # ── Navigation ───────────────────────────────────────────────────────────

    @abstractmethod
    async def navigate_to_application(self) -> bool:
        """
        Click through to the actual application form from the job posting page.
        Returns True when the form is ready to interact with.
        """
        ...

    # ── Form interaction ─────────────────────────────────────────────────────

    @abstractmethod
    async def get_form_fields(self) -> List[Dict[str, Any]]:
        """
        Return a list of form fields on the current page/step.
        Each dict has at minimum: {"label": str, "type": str, "selector": str}
        """
        ...

    @abstractmethod
    async def fill_text_field(self, selector: str, value: str) -> bool:
        """Type `value` into a text / textarea input."""
        ...

    @abstractmethod
    async def fill_select_field(self, selector: str, value: str) -> bool:
        """Select an option in a <select> or custom dropdown."""
        ...

    async def fill_file_field(self, selector: str, file_path: str) -> bool:
        """Upload a file (resume PDF). Default impl uses Playwright's set_input_files."""
        try:
            await self.page.set_input_files(selector, file_path)
            return True
        except Exception as e:
            print(f"[{self.platform_name}] File upload failed for {selector!r}: {e}")
            return False

    @abstractmethod
    async def submit(self) -> bool:
        """
        Click the final submit / apply button.
        Returns True if submission appeared successful.
        """
        ...

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def wait_for_navigation(self, timeout: int = 10_000) -> None:
        """Wait for the page to settle after a click."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            await self.page.wait_for_timeout(2000)

    async def safe_click(self, selector: str, timeout: int = 5_000) -> bool:
        """Click an element if it exists and is visible."""
        try:
            el = await self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            if el:
                await el.click()
                return True
        except Exception as e:
            print(f"[{self.platform_name}] safe_click({selector!r}) failed: {e}")
        return False

    async def safe_fill(self, selector: str, value: str) -> bool:
        """Fill a field if it exists."""
        try:
            el = await self.page.wait_for_selector(selector, timeout=5_000, state="visible")
            if el:
                await el.triple_click()
                await el.type(value, delay=30)
                return True
        except Exception as e:
            print(f"[{self.platform_name}] safe_fill({selector!r}) failed: {e}")
        return False

    async def element_exists(self, selector: str, timeout: int = 3_000) -> bool:
        """Return True if the selector matches a visible element."""
        try:
            el = await self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            return el is not None
        except Exception:
            return False

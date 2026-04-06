"""
ats/factory.py
==============
ATS handler factory.

Given a platform name string and a Playwright page, returns the
correct ATSHandler subclass. This is the single import the agent
nodes need — they never reference individual ATS classes directly.

Usage:
    from ats.factory import get_ats_handler

    handler = get_ats_handler(platform="workday", page=page, credentials=creds)
    await handler.sign_in()
    await handler.navigate_to_application()
    fields = await handler.get_form_fields()
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from ats.base import ATSHandler
from ats.workday import WorkdayHandler
from ats.greenhouse import GreenhouseHandler
from ats.lever import LeverHandler


# Registry — add new ATS platforms here
_REGISTRY: Dict[str, type[ATSHandler]] = {
    "workday":    WorkdayHandler,
    "greenhouse": GreenhouseHandler,
    "lever":      LeverHandler,
}


def get_ats_handler(
    platform: str,
    page,
    credentials: Optional[Dict[str, str]] = None,
) -> ATSHandler:
    """
    Return the correct ATSHandler for the given platform string.

    Args:
        platform:    "workday" | "greenhouse" | "lever" | "unknown"
        page:        Playwright Page object
        credentials: Optional dict of env vars; defaults to os.environ

    Returns:
        An instantiated ATSHandler ready to call sign_in() on.

    Raises:
        ValueError: if platform is not supported and fallback also fails.
    """
    if credentials is None:
        credentials = dict(os.environ)

    handler_class = _REGISTRY.get(platform.lower())

    if handler_class is None:
        print(f"[ats_factory] Unknown platform '{platform}' — using Greenhouse (generic) handler")
        handler_class = GreenhouseHandler  # Most generic / forgiving fallback

    return handler_class(page=page, credentials=credentials)


def supported_platforms() -> list[str]:
    """Return a list of all supported ATS platform names."""
    return list(_REGISTRY.keys())

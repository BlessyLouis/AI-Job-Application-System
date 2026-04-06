"""
agent/state.py
==============
Shared state object that flows through every node in the LangGraph graph.

All nodes READ from and RETURN updates to AgentState.
LangGraph merges the returned dict into the running state automatically.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """
    The single source of truth passed between every node.

    Fields are optional (total=False) so each node only needs to
    declare what it produces — LangGraph merges partial updates.
    """

    # ── Job being processed ──────────────────────────────────────────────────
    job_id:        int           # DB primary key of the current Job row
    job_url:       str           # URL of the job posting
    job_company:   str
    job_title:     str
    ats_platform:  str           # "workday" | "greenhouse" | "lever" | "unknown"

    # ── Candidate data (loaded from DB at start) ─────────────────────────────
    candidate_id:      int
    candidate_profile: Dict[str, Any]   # full Candidate row as dict
    custom_answers:    Dict[str, str]   # {key: value} flat lookup map

    # ── Generated artefacts ──────────────────────────────────────────────────
    job_description:       str           # scraped JD text
    tailored_resume_path:  str           # path to tailored PDF
    cover_letter_path:     str           # path to cover letter PDF
    cover_letter_text:     str           # raw text (for form fields that ask for it inline)

    # ── Browser / form state ─────────────────────────────────────────────────
    page:               Any              # Playwright Page object
    form_fields:        List[Dict]       # [{"label": "...", "type": "text|select|...", "element": ...}]
    filled_fields:      Dict[str, str]   # {label: value} of fields already filled
    unanswered_fields:  List[str]        # labels the agent could NOT fill

    # ── HITL ─────────────────────────────────────────────────────────────────
    hitl_question:      str              # the field label sent to the user
    hitl_answer:        Optional[str]    # user's response (None = timed out)

    # ── Control flow ─────────────────────────────────────────────────────────
    next_action:    str          # used by conditional edges: "continue" | "backlog" | "hitl"
    error_message:  str          # set when a node fails
    status:         str          # mirrors JobStatus enum values

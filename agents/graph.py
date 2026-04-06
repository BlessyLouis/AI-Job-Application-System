"""
agent/graph.py
==============
LangGraph state machine orchestrating the full job application pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from agents.state import AgentState
from agents.nodes.resume_tailor  import resume_tailor_node
from agents.nodes.cover_letter   import cover_letter_node
from agents.nodes.browser_launch import browser_launch_node
from agents.nodes.form_filler    import form_filler_node
from agents.nodes.hitl           import hitl_node, submitter_node
from db.database import get_session
from db.models import Candidate, CustomAnswer, Job, JobStatus


# ---------------------------------------------------------------------------
# load_candidate node
# ---------------------------------------------------------------------------

def load_candidate_node(state: AgentState) -> AgentState:
    candidate_id = state["candidate_id"]

    with get_session() as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            return {"error_message": f"Candidate {candidate_id} not found",
                    "next_action": "failed"}

        answers_rows = (
            session.query(CustomAnswer)
            .filter_by(candidate_id=candidate_id)
            .all()
        )
        custom_answers = {row.key: row.value for row in answers_rows}

        profile = {
            "full_name":    candidate.full_name,
            "email":        candidate.email,
            "phone":        candidate.phone,
            "location":     candidate.location,
            "linkedin_url": candidate.linkedin_url,
            "github_url":   candidate.github_url,
            "portfolio_url":candidate.portfolio_url,
            "resume_path":  candidate.resume_path,
            "work_history": candidate.work_history or [],
            "education":    candidate.education    or [],
            "skills":       candidate.skills       or [],
        }

    with get_session() as session:
        job = session.get(Job, state["job_id"])
        if job:
            job.status     = JobStatus.IN_PROGRESS
            job.started_at = datetime.utcnow()
            session.commit()

    print(f"[load_candidate] Loaded {profile['full_name']} "
          f"with {len(custom_answers)} custom answers")

    return {"candidate_profile": profile, "custom_answers": custom_answers}


# ---------------------------------------------------------------------------
# Terminal nodes
# ---------------------------------------------------------------------------

def mark_failed_node(state: AgentState) -> AgentState:
    reason = state.get("error_message", "Unknown error")
    print(f"[mark_failed] Job {state['job_id']} failed: {reason}")
    with get_session() as session:
        job = session.get(Job, state["job_id"])
        if job:
            job.status         = JobStatus.FAILED
            job.failure_reason = reason
            session.commit()
    return {"status": "failed"}


def mark_backlog_node(state: AgentState) -> AgentState:
    unanswered = state.get("unanswered_fields", [])
    print(f"[mark_backlog] Job {state['job_id']} → backlog. Unanswered: {unanswered}")
    with get_session() as session:
        job = session.get(Job, state["job_id"])
        if job:
            job.status            = JobStatus.BACKLOG
            job.unanswered_fields = unanswered
            session.commit()
    return {"status": "backlog"}


# ---------------------------------------------------------------------------
# Conditional edge routers
# ---------------------------------------------------------------------------

def route_after_browser(state: AgentState) -> str:
    return state.get("next_action", "continue")

def route_after_form_fill(state: AgentState) -> str:
    return state.get("next_action", "submit")

def route_after_hitl(state: AgentState) -> str:
    return state.get("next_action", "submit")


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("load_candidate",  load_candidate_node)
    graph.add_node("resume_tailor",   resume_tailor_node)
    graph.add_node("cover_letter",    cover_letter_node)
    graph.add_node("browser_launch",  browser_launch_node)
    graph.add_node("form_fill",       form_filler_node)
    graph.add_node("hitl",            hitl_node)
    graph.add_node("submit",          submitter_node)
    graph.add_node("mark_failed",     mark_failed_node)
    graph.add_node("mark_backlog",    mark_backlog_node)

    graph.add_edge(START,            "load_candidate")
    graph.add_edge("load_candidate", "resume_tailor")
    graph.add_edge("resume_tailor",  "cover_letter")
    graph.add_edge("cover_letter",   "browser_launch")

    graph.add_conditional_edges("browser_launch", route_after_browser,
        {"continue": "form_fill", "failed": "mark_failed"})

    graph.add_conditional_edges("form_fill", route_after_form_fill,
        {"submit": "submit", "hitl": "hitl", "failed": "mark_failed"})

    graph.add_conditional_edges("hitl", route_after_hitl,
        {"submit": "submit", "backlog": "mark_backlog"})

    graph.add_edge("submit",      END)
    graph.add_edge("mark_failed", END)
    graph.add_edge("mark_backlog",END)

    return graph


compiled_graph = build_graph().compile()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_job(job_id: int, candidate_id: int) -> Dict[str, Any]:
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        initial_state: AgentState = {
            "job_id":       job_id,
            "candidate_id": candidate_id,
            "job_url":      job.url,
            "job_company":  job.company or "",
            "job_title":    job.title   or "",
            "ats_platform": job.ats_platform or "unknown",
        }

    print(f"\n{'='*60}")
    print(f"Processing job {job_id}: {initial_state['job_url']}")
    print(f"{'='*60}\n")

    return compiled_graph.invoke(initial_state)

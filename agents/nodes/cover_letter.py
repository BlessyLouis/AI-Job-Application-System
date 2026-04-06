"""
agents/nodes/cover_letter.py
============================
Node 2: Generate a tailored cover letter using Groq (free).
"""

from __future__ import annotations

import os
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import AgentState
from db.database import get_session
from db.models import Job


SYSTEM_PROMPT = """
You are an expert career coach who writes compelling, authentic cover letters.
Rules:
- 3 paragraphs: (1) hook + why this company, (2) relevant experience, (3) close
- Sound human — no generic clichés
- Under 300 words
- Output ONLY the body text. No subject line, no greeting, no sign-off.
""".strip()


def _build_prompt(profile: dict, jd: str, company: str, title: str) -> str:
    work_summary = "; ".join(
        f"{w['title']} at {w['company']}" for w in profile.get("work_history", [])
    )
    skills = ", ".join(profile.get("skills", [])[:15])
    return (
        f"Candidate: {profile['full_name']}\n"
        f"Roles: {work_summary}\n"
        f"Skills: {skills}\n\n"
        f"Applying for: {title} at {company}\n\n"
        f"Job Description:\n{jd}\n\n"
        f"Write the cover letter body."
    )


def _write_pdf(text: str, profile: dict, company: str, title: str, out_path: str) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib import colors
    except ImportError:
        with open(out_path.replace(".pdf", ".txt"), "w") as f:
            f.write(text)
        return

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    name_s = ParagraphStyle("n", fontSize=13, fontName="Helvetica-Bold", spaceAfter=2)
    meta_s = ParagraphStyle("m", fontSize=9, textColor=colors.grey, spaceAfter=16)
    body_s = ParagraphStyle("b", fontSize=10, leading=16, spaceAfter=10)

    story = [
        Paragraph(profile["full_name"], name_s),
        Paragraph(" | ".join(filter(None, [profile.get("email"), profile.get("phone"), profile.get("location")])), meta_s),
        Paragraph(datetime.now().strftime("%B %d, %Y"), body_s),
        Paragraph(f"Hiring Team — {company}<br/>Re: {title}", body_s),
        Spacer(1, 8),
        Paragraph("Dear Hiring Team,", body_s),
    ]
    for para in text.strip().split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), body_s))
    story += [Spacer(1, 8), Paragraph("Sincerely,", body_s), Paragraph(profile["full_name"], name_s)]
    doc.build(story)


def cover_letter_node(state: AgentState) -> AgentState:
    print(f"[cover_letter] Generating cover letter for job_id={state['job_id']} ...")

    llm     = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.6)
    profile = state["candidate_profile"]
    jd      = state.get("job_description", "")
    company = state.get("job_company", "the company")
    title   = state.get("job_title", "the role")

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_prompt(profile, jd, company, title)),
        ])
        cl_text = response.content.strip()
    except Exception as e:
        print(f"[cover_letter] LLM error: {e} — using placeholder")
        cl_text = (
            f"I am excited to apply for the {title} role at {company}. "
            f"With strong experience in {', '.join(profile.get('skills', [])[:5])}, "
            f"I am confident I will make an immediate impact."
        )

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("outputs", "cover_letters")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"cover_letter_{state['job_id']}_{ts}.pdf")
    _write_pdf(cl_text, profile, company, title, out_path)

    with get_session() as session:
        job = session.get(Job, state["job_id"])
        if job:
            job.cover_letter_path = out_path
            session.commit()

    print(f"[cover_letter] Written to {out_path}")
    return {"cover_letter_text": cl_text, "cover_letter_path": out_path}

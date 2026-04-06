"""
agents/nodes/resume_tailor.py
==============================
Node 1: Tailor resume to job description using Groq (free).
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import AgentState
from db.database import get_session
from db.models import Job


SYSTEM_PROMPT = """
You are an expert technical resume writer.
Tailor the candidate's resume bullets to match the job description.
Rules:
- Never invent experience. Only rephrase and reorder existing info.
- Mirror the JD's language and priorities.
- Output ONLY a JSON object with this exact structure, no markdown, no preamble:
{
  "summary": "2-3 sentence professional summary",
  "work_history": [
    {"company": "...", "title": "...", "start": "...", "end": "...", "bullets": ["...", "..."]}
  ],
  "skills": ["skill1", "skill2"]
}
""".strip()


def _build_prompt(profile: dict, jd: str) -> str:
    work = "\n".join(
        f"- {w['title']} at {w['company']} ({w.get('start','')} - {w.get('end','present')}): {w.get('description','')}"
        for w in profile.get("work_history", [])
    )
    skills = ", ".join(profile.get("skills", []))
    edu = "; ".join(
        f"{e.get('degree','')} from {e.get('institution','')} ({e.get('graduation_year','')})"
        for e in profile.get("education", [])
    )
    return (
        f"Candidate: {profile['full_name']}\n"
        f"Work History:\n{work}\n\n"
        f"Education: {edu}\n"
        f"Skills: {skills}\n\n"
        f"Job Description:\n{jd}\n\n"
        f"Tailor the resume."
    )


def _write_pdf(tailored: dict, profile: dict, out_path: str) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib import colors
    except ImportError:
        with open(out_path.replace(".pdf", ".json"), "w") as f:
            json.dump(tailored, f, indent=2)
        return

    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=1.8*cm, rightMargin=1.8*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)
    name_s   = ParagraphStyle("name",   fontName="Helvetica-Bold", fontSize=20, spaceAfter=2)
    contact_s= ParagraphStyle("con",    fontName="Helvetica",      fontSize=8,  textColor=colors.grey, spaceAfter=8)
    h2_s     = ParagraphStyle("h2",     fontName="Helvetica-Bold", fontSize=9,  spaceBefore=8, spaceAfter=2)
    role_s   = ParagraphStyle("role",   fontName="Helvetica-Bold", fontSize=9,  spaceAfter=1)
    meta_s   = ParagraphStyle("meta",   fontName="Helvetica-Oblique", fontSize=8, textColor=colors.grey, spaceAfter=2)
    bullet_s = ParagraphStyle("bullet", fontName="Helvetica",      fontSize=8,  leftIndent=10, spaceAfter=1)
    body_s   = ParagraphStyle("body",   fontName="Helvetica",      fontSize=8,  spaceAfter=3)

    def rule():
        return HRFlowable(width="100%", thickness=0.4, color=colors.lightgrey, spaceAfter=3)

    story = []
    story.append(Paragraph(profile["full_name"], name_s))
    story.append(Paragraph(
        " · ".join(filter(None, [profile.get("email"), profile.get("phone"), profile.get("location")])),
        contact_s
    ))

    if tailored.get("summary"):
        story += [Paragraph("SUMMARY", h2_s), rule(), Paragraph(tailored["summary"], body_s)]

    if tailored.get("work_history"):
        story += [Paragraph("EXPERIENCE", h2_s), rule()]
        for job in tailored["work_history"]:
            story.append(Paragraph(f"<b>{job.get('title','')}</b> — {job.get('company','')}  ({job.get('start','')} – {job.get('end','present')})", role_s))
            for b in job.get("bullets", []):
                story.append(Paragraph(f"• {b}", bullet_s))
            story.append(Spacer(1, 4))

    if tailored.get("skills"):
        story += [Paragraph("SKILLS", h2_s), rule(),
                  Paragraph(", ".join(tailored["skills"]), body_s)]

    if profile.get("education"):
        story += [Paragraph("EDUCATION", h2_s), rule()]
        for e in profile["education"]:
            story.append(Paragraph(
                f"<b>{e.get('degree','')}</b> — {e.get('institution','')} ({e.get('graduation_year','')})",
                role_s
            ))

    doc.build(story)


def resume_tailor_node(state: AgentState) -> AgentState:
    print(f"[resume_tailor] Tailoring resume for job_id={state['job_id']} ...")

    llm     = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
    profile = state["candidate_profile"]
    jd      = state.get("job_description", "")

    if not jd:
        print("[resume_tailor] No job description in state — using generic tailoring.")

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_prompt(profile, jd)),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        tailored = json.loads(raw)
    except Exception as e:
        print(f"[resume_tailor] LLM error: {e} — using base resume")
        tailored = {
            "summary": "",
            "work_history": profile.get("work_history", []),
            "skills": profile.get("skills", []),
        }

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("outputs", "resumes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"tailored_{state['job_id']}_{ts}.pdf")
    _write_pdf(tailored, profile, out_path)

    with get_session() as session:
        job = session.get(Job, state["job_id"])
        if job:
            job.tailored_resume_path = out_path
            session.commit()

    print(f"[resume_tailor] Written to {out_path}")
    return {"tailored_resume_path": out_path}

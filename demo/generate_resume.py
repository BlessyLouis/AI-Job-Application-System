"""
demo/generate_resume.py
=======================
Generates the base resume PDF for the demo candidate (Aryan Mehta).
Run once as part of demo setup:

    python -m demo.generate_resume

Outputs: demo/resumes/aryan_mehta_base.pdf
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)


# ── Colour palette ─────────────────────────────────────────────────────────────
INK    = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#16213e")
MUTED  = colors.HexColor("#6c757d")
RULE   = colors.HexColor("#dee2e6")


# ── Style factory ──────────────────────────────────────────────────────────────

def _styles() -> dict:
    return {
        "name":    ParagraphStyle("name",    fontName="Helvetica-Bold",   fontSize=22, leading=26, textColor=INK,    spaceAfter=2),
        "tagline": ParagraphStyle("tagline", fontName="Helvetica",        fontSize=10, leading=14, textColor=MUTED,  spaceAfter=4),
        "contact": ParagraphStyle("contact", fontName="Helvetica",        fontSize=8.5,leading=12, textColor=MUTED,  spaceAfter=10),
        "h2":      ParagraphStyle("h2",      fontName="Helvetica-Bold",   fontSize=9,  leading=12, textColor=ACCENT, spaceBefore=10, spaceAfter=3),
        "role":    ParagraphStyle("role",    fontName="Helvetica-Bold",   fontSize=9.5,leading=13, textColor=INK,    spaceAfter=1),
        "meta":    ParagraphStyle("meta",    fontName="Helvetica-Oblique",fontSize=8.5,leading=12, textColor=MUTED,  spaceAfter=3),
        "bullet":  ParagraphStyle("bullet",  fontName="Helvetica",        fontSize=8.5,leading=13, textColor=INK,    leftIndent=10, spaceAfter=1),
        "body":    ParagraphStyle("body",    fontName="Helvetica",        fontSize=8.5,leading=13, textColor=INK,    spaceAfter=4),
        "skill":   ParagraphStyle("skill",   fontName="Helvetica",        fontSize=8.5,leading=13, textColor=INK,    spaceAfter=2),
    }


def _rule() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=4, spaceBefore=2)


def _section(title: str, s: dict) -> list:
    return [Paragraph(title.upper(), s["h2"]), _rule()]


# ── Builder ────────────────────────────────────────────────────────────────────

def generate(out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.8*cm,  bottomMargin=1.8*cm,
    )
    s = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Aryan Mehta", s["name"]))
    story.append(Paragraph("Software Engineer  ·  Backend &amp; ML Systems", s["tagline"]))
    story.append(Paragraph(
        "aryan.mehta.dev@gmail.com  ·  +91-98765-43210  ·  Bengaluru, India  ·  "
        "linkedin.com/in/aryanmehta-dev  ·  github.com/aryanmehta-dev",
        s["contact"],
    ))

    # ── Summary ───────────────────────────────────────────────────────────────
    story += _section("Professional Summary", s)
    story.append(Paragraph(
        "Backend engineer with 3+ years building high-throughput distributed systems at fintech scale. "
        "Experienced in Python, FastAPI, and Kafka-based event-driven architectures. "
        "Recently focused on LLM-powered tooling and agentic pipeline design using LangChain and LangGraph.",
        s["body"],
    ))

    # ── Experience ────────────────────────────────────────────────────────────
    story += _section("Experience", s)

    # Razorpay
    story.append(Paragraph("Software Engineer II — Razorpay", s["role"]))
    story.append(Paragraph("Jul 2022 – Present  ·  Bengaluru, India", s["meta"]))
    for b in [
        "Owned core payment-processing microservices handling <b>2M+ transactions/day</b> at 99.95% uptime.",
        "Reduced p99 API latency by <b>35%</b> migrating hot-path calls to async Kafka workers.",
        "Led migration of 4 monolith modules to event-driven microservices, cutting deployment coupling by 60%.",
        "Built an internal fraud-detection rule engine that blocked $1.2M in fraud in Q3 2023.",
        "Mentored 2 junior engineers; introduced Architecture Decision Records (ADR) practice to the team.",
    ]:
        story.append(Paragraph(f"&bull;  {b}", s["bullet"]))
    story.append(Spacer(1, 6))

    # Zoho
    story.append(Paragraph("Software Engineer — Zoho Corporation", s["role"]))
    story.append(Paragraph("Jul 2021 – Jun 2022  ·  Chennai, India", s["meta"]))
    for b in [
        "Developed REST APIs for Zoho CRM's email integration module in Java (Spring Boot).",
        "Improved unit test coverage from <b>41% to 87%</b> and reduced CI build time by 20%.",
        "Shipped 3 customer-requested features within one sprint cycle in collaboration with product.",
    ]:
        story.append(Paragraph(f"&bull;  {b}", s["bullet"]))
    story.append(Spacer(1, 4))

    # ── Projects ──────────────────────────────────────────────────────────────
    story += _section("Projects", s)
    for pname, ptech, pdesc in [
        (
            "AI Job Application Agent",
            "Python · LangGraph · Playwright · GPT-4o",
            "End-to-end agentic pipeline that autonomously tailors resumes, generates cover letters, "
            "detects ATS platforms (Workday, Greenhouse, Lever), fills forms, and submits with HITL escalation.",
        ),
        (
            "FinSight — Financial Analytics Dashboard",
            "FastAPI · PostgreSQL · Redis · React",
            "Real-time portfolio analytics platform processing 500K+ price ticks/day with sub-100ms P95 latency.",
        ),
    ]:
        story.append(Paragraph(
            f"<b>{pname}</b>  <font color='#6c757d' size='8'>{ptech}</font>",
            s["body"],
        ))
        story.append(Paragraph(pdesc, s["bullet"]))
        story.append(Spacer(1, 3))

    # ── Education ─────────────────────────────────────────────────────────────
    story += _section("Education", s)
    story.append(Paragraph(
        "B.Tech in Computer Science &amp; Engineering — NIT Trichy", s["role"]
    ))
    story.append(Paragraph("2017 – 2021  ·  GPA: 8.6 / 10.0", s["meta"]))

    # ── Skills ────────────────────────────────────────────────────────────────
    story += _section("Technical Skills", s)
    for grp, items in [
        ("Languages",     "Python, Java, SQL, Bash"),
        ("Frameworks",    "FastAPI, Django, Spring Boot, LangChain, LangGraph"),
        ("Infra / Cloud", "AWS (EC2, S3, SQS, Lambda), Docker, Kubernetes, GitHub Actions"),
        ("Databases",     "PostgreSQL, Redis, Elasticsearch, SQLAlchemy"),
        ("Messaging",     "Apache Kafka, RabbitMQ"),
        ("AI / ML",       "OpenAI API, LangChain, LangGraph, Playwright, Pydantic"),
    ]:
        story.append(Paragraph(f"<b>{grp}:</b>  {items}", s["skill"]))

    doc.build(story)
    print(f"[generate_resume] ✅ Written → {out_path}")
    return out_path


if __name__ == "__main__":
    generate("demo/resumes/aryan_mehta_base.pdf")

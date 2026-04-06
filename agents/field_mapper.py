"""
agents/field_mapper.py
======================
Fixed: boolean questions now return Yes/No not country names.
Fixed: work authorization returns Yes (authorized in India).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage


@dataclass
class FieldResolution:
    label:      str
    value:      Optional[str]
    tier:       str
    confidence: float


def _normalise_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _resolve_from_profile(label: str, profile: Dict[str, Any]) -> Optional[str]:
    l = label.lower().strip()

    full_name  = profile.get("full_name", "")
    name_parts = full_name.split()
    first      = name_parts[0] if name_parts else ""
    last       = name_parts[-1] if len(name_parts) > 1 else ""

    work_history = profile.get("work_history", [])
    education    = profile.get("education", [{}])
    skills_list  = profile.get("skills", [])

    loc = profile.get("location", "Bengaluru, Karnataka, India")
    loc_parts = [p.strip() for p in loc.split(",")]
    city    = loc_parts[0] if loc_parts else "Bengaluru"
    state   = loc_parts[1] if len(loc_parts) > 1 else "Karnataka"
    country = loc_parts[-1] if loc_parts else "India"

    # ── Name ──────────────────────────────────────────────────────────────
    if re.search(r"\bfirst[\s_]?name\b|given[\s_]?name|forename", l):
        return first
    if re.search(r"\blast[\s_]?name\b|family[\s_]?name|surname", l):
        return last
    if re.search(r"preferred[\s_]?(first[\s_]?)?name|nickname|goes[\s_]?by", l):
        return first
    if re.search(r"\bfull[\s_]?name\b", l):
        return full_name
    if l in ("name", "your name", "applicant name"):
        return full_name
    if re.search(r"^\bname\b", l) and "last" not in l and "first" not in l:
        return full_name

    # ── Contact ───────────────────────────────────────────────────────────
    if re.search(r"\bemail\b|e[\s-]?mail|email[\s_]?address", l):
        return profile.get("email", "")
    if re.search(r"\bphone\b|\bmobile\b|telephone|contact[\s_]?number|cell", l):
        return profile.get("phone", "")

    # ── Location ──────────────────────────────────────────────────────────
    if re.search(r"\bcountry\b", l):
        return country
    if re.search(r"\bstate\b|\bprovince\b", l) and "veteran" not in l and "disability" not in l:
        return state
    if re.search(r"\bcity\b|\btown\b", l):
        return city
    if re.search(r"\blocation\b|where.*based|plan.*work|intend.*work|address.*work|current.*address", l):
        return loc
    if re.search(r"\bcounty\b", l):
        return country

    # ── Social / web ──────────────────────────────────────────────────────
    if re.search(r"linkedin", l):
        return profile.get("linkedin_url", "")
    if re.search(r"github", l):
        return profile.get("github_url", "")
    if re.search(r"portfolio|personal.*site|other.*website|other.*url|other.*web", l):
        return profile.get("portfolio_url", "")
    if re.search(r"\bwebsite\b|\burl\b", l) and "linkedin" not in l and "github" not in l:
        return profile.get("portfolio_url", "")

    # ── Work history ──────────────────────────────────────────────────────
    if re.search(r"current.*company|employer|organization|company.*name|where.*work", l):
        return work_history[0].get("company", "") if work_history else ""
    if re.search(r"current.*title|current.*role|job[\s_]?title|position", l):
        return work_history[0].get("title", "") if work_history else ""
    if re.search(r"years.*experience|experience.*years|how many years|total.*experience", l):
        return "3"
    if re.search(r"\borg\b|companies.*worked|previous.*employer", l):
        return ", ".join(w.get("company", "") for w in work_history) if work_history else ""

    # ── Education ─────────────────────────────────────────────────────────
    edu = education[0] if education else {}
    if re.search(r"degree|qualification|highest.*edu|education.*level", l):
        return edu.get("degree", "B.Tech")
    if re.search(r"university|college|institution|school", l):
        return edu.get("institution", "NIT Trichy")
    if re.search(r"graduation.*year|year.*grad|grad.*year", l):
        return str(edu.get("graduation_year", "2021"))
    if re.search(r"\bgpa\b|grade.*point|cgpa", l):
        return str(edu.get("gpa", "8.6"))
    if re.search(r"\bfield\b.*study|major|specializ", l):
        return edu.get("field", "Computer Science")

    # ── Skills ────────────────────────────────────────────────────────────
    if re.search(r"primary.*language|coding.*language|programming.*language|language.*prefer", l):
        return "Python"
    if re.search(r"\bskills\b", l):
        return ", ".join(skills_list[:8])

    # ── Boolean questions — MUST return Yes/No not country names ──────────
    # Work authorization (boolean — are you authorized?)
    if re.search(r"authorized.*work|authorised.*work|eligible.*work|right to work|work.*authoriz", l):
        # They're asking if candidate is authorized — yes in India
        return "Yes"

    # Visa sponsorship (boolean — do you need it?)
    if re.search(r"require.*sponsor|need.*sponsor|visa.*sponsor|sponsor.*visa", l):
        return "No"

    # Relocation
    if re.search(r"open.*reloc|willing.*reloc|reloc.*role|consider.*reloc", l):
        return "Yes"

    # In-person / onsite
    if re.search(r"open.*in.person|onsite.*25|office.*25|in.person.*office|work.*office", l):
        return "Yes"

    # Worked here before
    if re.search(r"worked.*before|work.*previously|previous.*employee|former.*employee", l):
        return "No"

    # Interviewed before
    if re.search(r"interview.*before|previously.*interview|interviewed.*at", l):
        return "No"

    return None


def _resolve_from_custom(label: str, custom_answers: Dict[str, str]) -> Optional[str]:
    label_key = _normalise_key(label)

    if label_key in custom_answers:
        return custom_answers[label_key]

    for key, value in custom_answers.items():
        if key in label_key or label_key in key:
            return value

    l = label.lower()
    keyword_map = {
        "sponsorship_required":       ["sponsorship", "visa sponsor", "work permit"],
        "notice_period_days":         ["notice period", "when can you start", "availability"],
        "earliest_start_date":        ["start date", "when.*start", "join.*date"],
        "salary_expectation_inr_lpa": ["salary", "compensation", "ctc", "remuneration"],
        "willing_to_relocate":        ["relocat"],
        "remote_preference":          ["remote", "work from home", "hybrid"],
        "gender":                     ["gender", "eeo.*gender"],
        "veteran_status":             ["veteran", "eeo.*veteran"],
        "disability_status":          ["disability", "disabled"],
        "how_did_you_hear":           ["how did you hear", "how.*find", "referral"],
        "highest_education_level":    ["education level", "highest.*degree"],
        "years_experience_total":     ["years.*experience", "experience.*years"],
        "coding_language_preference": ["coding language", "language preference", "preferred language"],
        "why_anthropic":              ["why anthropic"],
        "why_figma":                  ["why figma"],
        "why_do_you_want":            ["why do you want", "why.*join", "why.*role", "why.*company"],
        "additional_information":     ["additional information", "anything else"],
        "pronouns":                   ["pronouns"],
        "hispanic_latino":            ["hispanic", "latino"],
        "race":                       ["race", "ethnicity"],
    }

    for key_prefix, triggers in keyword_map.items():
        if any(re.search(t, l) for t in triggers):
            for k, v in custom_answers.items():
                if k == key_prefix or k.startswith(key_prefix) or key_prefix.startswith(k):
                    return v

    return None


LLM_SYSTEM = """
You are filling out a job application form on behalf of a candidate based in India.
Given the candidate profile and a form field, provide the best concise answer.

Critical rules:
- For YES/NO questions: answer exactly "Yes" or "No"
- For "Are you authorized to work...": answer "Yes" (candidate is authorized in India)  
- For "Do you require visa sponsorship": answer "No"
- For "Are you open to working in-person/onsite": answer "Yes"
- For "Are you open to relocation": answer "Yes"
- For race/ethnicity dropdowns: answer "Decline to state"
- For disability: answer "I don't have a disability" or "No disability"
- For veteran: answer "I am not a protected veteran" or "Not a veteran"
- Never answer with a country name for a yes/no question
- If you cannot answer: respond ESCALATE
- Respond ONLY with the answer. No explanation.
""".strip()


def _resolve_from_llm(label, profile, custom_answers, jd, company, title) -> FieldResolution:
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

    work = "; ".join(f"{w.get('title','')} at {w.get('company','')}" for w in profile.get("work_history", []))
    edu  = "; ".join(f"{e.get('degree','')} from {e.get('institution','')}" for e in profile.get("education", []))

    prompt = (
        f"Candidate: {profile.get('full_name','')}, based in {profile.get('location','India')}\n"
        f"Work: {work}\nEducation: {edu}\n"
        f"Skills: {', '.join(profile.get('skills', []))}\n"
        f"Custom answers: {custom_answers}\n\n"
        f"Applying for: {title} at {company}\n\n"
        f"Form field: \"{label}\"\nAnswer:"
    )

    try:
        resp = llm.invoke([SystemMessage(content=LLM_SYSTEM), HumanMessage(content=prompt)])
        ans  = resp.content.strip()
        if ans.upper() == "ESCALATE" or not ans:
            return FieldResolution(label=label, value=None, tier="hitl", confidence=0.0)
        return FieldResolution(label=label, value=ans, tier="llm", confidence=0.75)
    except Exception as e:
        print(f"[field_mapper] LLM error for '{label}': {e}")
        return FieldResolution(label=label, value=None, tier="hitl", confidence=0.0)


def resolve_field(label, profile, custom_answers, jd="", company="", title="") -> FieldResolution:
    val = _resolve_from_profile(label, profile)
    if val:
        return FieldResolution(label=label, value=val, tier="profile", confidence=1.0)

    val = _resolve_from_custom(label, custom_answers)
    if val:
        return FieldResolution(label=label, value=val, tier="custom", confidence=1.0)

    return _resolve_from_llm(label, profile, custom_answers, jd, company, title)


def resolve_all_fields(form_fields, profile, custom_answers, jd="", company="", title=""):
    filled:      Dict[str, str] = {}
    hitl_labels: List[str]      = []

    for field in form_fields:
        label = field.get("label", "").strip()
        if not label:
            continue
        res = resolve_field(label, profile, custom_answers, jd, company, title)
        if res.tier == "hitl" or res.value is None:
            hitl_labels.append(label)
        else:
            filled[label] = res.value

    return filled, hitl_labels, []

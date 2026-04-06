"""
demo/seed_user.py — Seeds demo candidate + jobs.
Run: python -m demo.seed_user
"""

from db.database import init_db, get_session
from db.models import Candidate, CustomAnswer, Job, JobStatus, ATSPlatform


DEMO_CANDIDATE = {
    "full_name":     "Aryan Mehta",
    "email":         "aryan.mehta.dev@gmail.com",
    "phone":         "+91-98765-43210",
    "location":      "Bengaluru, Karnataka, India",
    "linkedin_url":  "https://linkedin.com/in/aryanmehta-dev",
    "github_url":    "https://github.com/aryanmehta-dev",
    "portfolio_url": "https://aryanmehta.dev",
    "resume_path":   "demo/resumes/aryan_mehta_base.pdf",
    "work_history": [
        {
            "company":     "Razorpay",
            "title":       "Software Engineer II",
            "start":       "2022-07",
            "end":         "present",
            "description": "Built payment processing microservices handling 2M+ transactions/day using Python and FastAPI.",
        },
        {
            "company":     "Zoho Corporation",
            "title":       "Software Engineer",
            "start":       "2021-07",
            "end":         "2022-06",
            "description": "Developed REST APIs for Zoho CRM email integration in Java Spring Boot.",
        },
    ],
    "education": [
        {
            "institution":     "NIT Trichy",
            "degree":          "B.Tech",
            "field":           "Computer Science",
            "graduation_year": 2021,
            "gpa":             8.6,
        }
    ],
    "skills": [
        "Python", "FastAPI", "LangChain", "LangGraph",
        "PostgreSQL", "Docker", "AWS", "Java", "Playwright",
    ],
}


DEMO_CUSTOM_ANSWERS = [
    # Eligibility
    ("sponsorship_required",        "No",                    "Indian citizen"),
    ("us_work_authorization",       "No",                    "Not authorized for US"),
    ("willing_to_relocate",         "Yes",                   None),
    ("willing_to_work_onsite",      "Yes",                   None),
    ("remote_preference",           "Hybrid or Remote",      None),

    # Timing
    ("notice_period_days",          "30",                    "Standard notice"),
    ("earliest_start_date",         "2 weeks from offer",    None),

    # Compensation
    ("salary_expectation_inr_lpa",  "28",                    "Targeting 28-32 LPA"),

    # Experience
    ("years_experience_total",      "3",                     None),
    ("years_experience_python",     "4",                     None),

    # Demographics (EEO)
    ("gender",                      "Male",                  None),
    ("veteran_status",              "Not a veteran",         None),
    ("disability_status",           "No disability",         None),
    ("hispanic_latino",             "No",                    None),
    ("race",                        "Decline to state",      None),
    ("pronouns",                    "He/Him",                None),

    # Sourcing
    ("how_did_you_hear",            "LinkedIn",              None),

    # Education
    ("highest_education_level",     "Bachelor's Degree",     None),

    # Common application questions
    ("have_worked_here_before",     "No",                    None),
    ("interviewed_here_before",     "No",                    None),
    ("agree_to_background_check",   "Yes",                   None),
    ("coding_language_preference",  "Python",                None),

    # Anthropic-specific
    ("why_anthropic",
     "I'm drawn to Anthropic's mission of building safe and beneficial AI. "
     "My experience building agentic pipelines with LangGraph aligns directly "
     "with the kind of work happening here, and I want to contribute to systems "
     "that are both powerful and trustworthy.",
     None),

    # Figma-specific
    ("why_figma",
     "Figma has transformed how product teams collaborate. As an engineer who "
     "has worked closely with designers, I've seen firsthand how Figma removes "
     "friction in the design-to-engineering handoff. I want to help build the "
     "platform that millions of creators depend on.",
     None),

    # Generic "why company"
    ("why_do_you_want",
     "I am excited about this role because it aligns with my background in "
     "building scalable backend systems and my interest in working on impactful "
     "products with a strong engineering culture.",
     None),

    # Additional info
    ("additional_information",
     "I am a quick learner and have a strong track record of delivering "
     "high-quality software in fast-paced environments.",
     None),
]


DEMO_JOBS = [
    {
        "url":          "https://job-boards.greenhouse.io/anthropic/jobs/4899511008",
        "company":      "Anthropic",
        "title":        "Software Engineer",
        "ats_platform": ATSPlatform.GREENHOUSE,
    },
    {
        "url":          "https://job-boards.greenhouse.io/figma/jobs/5691886004?gh_jid=5691886004",
        "company":      "Figma",
        "title":        "Software Engineer, Platform",
        "ats_platform": ATSPlatform.GREENHOUSE,
    },
    {
        "url":          "https://jobs.lever.co/zoox/11c7231c-0b37-4e6d-8a12-9a44e019a956",
        "company":      "Zoox",
        "title":        "Senior Software Engineer",
        "ats_platform": ATSPlatform.LEVER,
    },
    {
        "url":          "https://jobs.lever.co/veeva/8fe22df0-02b4-453d-919c-c8998cf913f6",
        "company":      "Veeva",
        "title":        "Associate Software Engineer",
        "ats_platform": ATSPlatform.LEVER,
    },
]


def seed():
    init_db()
    with get_session() as db:
        existing = db.query(Candidate).filter_by(email=DEMO_CANDIDATE["email"]).first()
        if existing:
            print("[Seed] Candidate exists — updating custom answers.")
            # Update/add custom answers for existing candidate
            for key, value, note in DEMO_CUSTOM_ANSWERS:
                ans = db.query(CustomAnswer).filter_by(
                    candidate_id=existing.id, key=key).first()
                if ans:
                    ans.value = value
                else:
                    db.add(CustomAnswer(candidate_id=existing.id,
                                        key=key, value=value, notes=note))
            print(f"[Seed] Updated {len(DEMO_CUSTOM_ANSWERS)} custom answers")
            return

        candidate = Candidate(**DEMO_CANDIDATE)
        db.add(candidate)
        db.flush()
        print(f"[Seed] Created: {candidate.full_name} (id={candidate.id})")

        for key, value, note in DEMO_CUSTOM_ANSWERS:
            db.add(CustomAnswer(candidate_id=candidate.id, key=key,
                                value=value, notes=note))
        print(f"[Seed] Inserted {len(DEMO_CUSTOM_ANSWERS)} custom answers")

        for job_data in DEMO_JOBS:
            db.add(Job(candidate_id=candidate.id,
                       status=JobStatus.QUEUED, **job_data))
        print(f"[Seed] Queued {len(DEMO_JOBS)} jobs")

    print("[Seed] Done.")


if __name__ == "__main__":
    seed()

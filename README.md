# AI-Job-Application-System

# AI Job Application Agent

An end-to-end agentic pipeline that autonomously handles the entire job application process. Given a queue of job URLs, it tailors a resume, generates a cover letter, opens a real browser, detects the ATS platform, fills every form field intelligently, and submits — with human-in-the-loop escalation for ambiguous fields.

---

## Table of Contents

1. [How to Run the Demo](#1-how-to-run-the-demo)
2. [Candidate Database — Structure & Extension](#2-candidate-database--structure--extension)
3. [ATS Detection](#3-ats-detection)
4. [Form Field Mapping](#4-form-field-mapping)
5. [Human-in-the-Loop (HITL)](#5-human-in-the-loop-hitl)
6. [Scaling to Multiple Users & Concurrent Agents](#6-scaling-to-multiple-users--concurrent-agents)
7. [Project Structure](#7-project-structure)

---

## 1. How to Run the Demo

### Prerequisites

```bash
python 3.11+
```

### Installation

```bash
# Clone the repo
git clone https://github.com/your-username/ai-job-agent.git
cd ai-job-agent

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Configuration

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
GROQ_API_KEY=gsk_...                # required — free at console.groq.com (no credit card)

# ATS credentials (for platforms that require sign-in)
WORKDAY_EMAIL=your@email.com
WORKDAY_PASSWORD=yourpassword

GREENHOUSE_EMAIL=your@email.com
GREENHOUSE_PASSWORD=yourpassword

LEVER_EMAIL=your@email.com
LEVER_PASSWORD=yourpassword

HEADLESS=false                  # set true to run browser invisibly (e.g. on a server)
```

> Credentials are read from `.env` only. They are never written into code.

### Seed the Demo Data

```bash
# Generates the demo resume PDF
python -m demo.generate_resume

# Seeds candidate profile, custom answers, and 6 job URLs into the database
python -m demo.seed_user
```

This creates:
- A realistic mid-level software engineer candidate (Aryan Mehta, 3 years exp)
- 25 pre-filled custom answers covering every common form question category
- 6 real job URLs across Workday, Greenhouse, and Lever

### Run the Agent

```bash
# Process all queued jobs for candidate 1 (the seeded demo user)
python main.py

# Process jobs for a specific candidate
python main.py --candidate-id 2

# Process a single specific job
python main.py --job-id 3
```

The agent prints live progress for every step: resume tailoring, ATS detection, field filling, HITL prompts, and submission confirmation.

---

## 2. Candidate Database — Structure & Extension

### Schema Overview

The database has three tables:

**`candidates`** — Core user profile.

| Column | Type | Description |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `full_name`, `email`, `phone` | String | Personal info |
| `location`, `linkedin_url`, `github_url` | String | Contact/social |
| `resume_path` | String | Path to base PDF resume on disk |
| `work_history` | JSON | List of `{company, title, start, end, description}` |
| `education` | JSON | List of `{institution, degree, field, graduation_year, gpa}` |
| `skills` | JSON | List of skill strings |

**`custom_answers`** — Key-value store for form fields not on any resume.

| Column | Type | Description |
|---|---|---|
| `candidate_id` | FK → candidates | Owner |
| `key` | String | Normalised snake_case label, e.g. `sponsorship_required` |
| `value` | Text | Always stored as text; agent casts as needed |
| `notes` | Text | Optional human annotation |

**`jobs`** — One row per application attempt.

| Column | Type | Description |
|---|---|---|
| `url`, `company`, `title` | String | Job metadata |
| `ats_platform` | Enum | `workday` / `greenhouse` / `lever` / `linkedin` / `unknown` |
| `status` | Enum | `queued` → `in_progress` → `submitted` / `failed` / `backlog` |
| `failure_reason` | Text | Set when `status = failed` |
| `unanswered_fields` | JSON | Field labels the agent could not fill |
| `tailored_resume_path`, `cover_letter_path` | String | Paths to generated artefacts |

### How to Add a New Job to the Queue

```python
from db.database import get_session, init_db
from db.models import Job, ATSPlatform, JobStatus

init_db()
with get_session() as session:
    session.add(Job(
        candidate_id=1,
        url="https://boards.greenhouse.io/stripe/jobs/9999",
        company="Stripe",
        title="Backend Engineer",
        ats_platform=ATSPlatform.GREENHOUSE,
        status=JobStatus.QUEUED,
    ))
    session.commit()
```

### How to Add a New Custom Answer

No code changes required. Just insert a row:

```python
from db.database import get_session
from db.models import CustomAnswer

with get_session() as session:
    session.add(CustomAnswer(
        candidate_id=1,
        key="years_experience_kubernetes",
        value="2",
        notes="Added before applying to DevOps-heavy roles",
    ))
    session.commit()
```

From the next run onwards, every form field whose label matches `years_experience_kubernetes` (exact, substring, or keyword match) will be auto-filled with `"2"` — no restarts, no code changes.

### Common Custom Answer Keys

| Key | Example Value |
|---|---|
| `sponsorship_required` | `No` |
| `notice_period_days` | `30` |
| `salary_expectation_inr_lpa` | `28` |
| `willing_to_relocate` | `Yes` |
| `how_did_you_hear` | `LinkedIn` |
| `us_work_authorization` | `No` |
| `gender` | `Male` |
| `years_experience_python` | `4` |

---

## 3. ATS Detection

The agent detects which ATS platform is serving a job posting using a two-stage approach — no hardcoded per-URL logic.

### Stage 1 — URL Pattern Matching

Regex patterns identify the ATS from the job URL before the page even loads:

| Pattern | ATS |
|---|---|
| `myworkday.com`, `wd*.myworkdayjobs.com` | Workday |
| `greenhouse.io`, `boards.greenhouse.io` | Greenhouse |
| `jobs.lever.co` | Lever |
| `linkedin.com/jobs` | LinkedIn |

### Stage 2 — DOM Fingerprinting

If the URL doesn't match, the agent inspects the rendered DOM for unique selectors each ATS injects:

| CSS Selector | ATS |
|---|---|
| `[data-automation-id="jobPostingHeader"]` | Workday |
| `.greenhouse-job-board`, `#greenhouse-app` | Greenhouse |
| `.lever-job-description` | Lever |
| `.jobs-apply-button--top` | LinkedIn |

This generalises across any domain — a company can host Workday at their own subdomain and it will still be detected correctly via DOM fingerprint.

### Adding a New ATS

1. Create `ats/newplatform.py` implementing the `ATSHandler` base class
2. Add one line to the registry in `ats/factory.py`:

```python
_REGISTRY: Dict[str, type[ATSHandler]] = {
    "workday":     WorkdayHandler,
    "greenhouse":  GreenhouseHandler,
    "lever":       LeverHandler,
    "newplatform": NewPlatformHandler,   # ← add here
}
```

3. Add its URL pattern to `ATS_URL_PATTERNS` and/or a DOM selector to `ATS_DOM_FINGERPRINTS` in `agent/nodes/browser_launch.py`

Nothing else changes.

---

## 4. Form Field Mapping

Every form field is resolved through a **4-tier precedence chain**. The agent works down the chain and stops at the first match.

```
Form field label
      │
      ▼
Tier 1 — Candidate Profile DB
      │  personal info, work history, education, skills
      │  (keyword matching: "email" → candidate.email)
      │
      ├── MATCHED → fill field ✅
      │
      ▼
Tier 2 — Custom Answers Table
      │  key-value store: sponsorship, salary, notice period, ...
      │  (exact key match → substring match → keyword fuzzy match)
      │
      ├── MATCHED → fill field ✅
      │
      ▼
Tier 3 — LLM Inference (GPT-4o)
      │  given the full candidate profile + job context,
      │  infer the most reasonable answer
      │  if confidence is low → returns "ESCALATE"
      │
      ├── CONFIDENT → fill field ✅
      │
      ▼
Tier 4 — HITL Escalation
         agent pauses and asks the user (30-second countdown)
```

### What Gets Logged

Any field that reaches Tier 4 and times out is written to `jobs.unanswered_fields` as a JSON list:

```json
["Work authorization in Germany", "Years of Kubernetes experience"]
```

After the run, the user sees exactly which keys to add to `custom_answers` before retrying.

---

## 5. Human-in-the-Loop (HITL)

HITL fires only when a form field cannot be resolved by profile data, custom answers, or LLM inference with confidence.

### Flow

```
Agent encounters ambiguous field
          │
          ▼
Prints field label to terminal with 30-second countdown
          │
    ┌─────┴─────┐
    │           │
User answers   Timeout / blank
    │           │
    ▼           ▼
Fill field    Job → BACKLOG
Save answer   Log unanswered fields
to custom_    Move to next job
answers DB    immediately
    │
    ▼
Continue form filling
```

### Terminal Appearance

```
============================================================
🤖 AGENT NEEDS YOUR INPUT
============================================================
Field: Work authorization status in Germany
You have 30 seconds to answer. Press Enter to submit.
(Leave blank + Enter to skip and move this job to backlog)
============================================================
⏱  23s remaining — Your answer: No, not authorised
```

### Answer Persistence

When the user answers, the value is immediately saved to the `custom_answers` table. On all future runs, that field will be resolved at Tier 2 without ever reaching HITL again — no code changes needed.

### Backlog Behaviour

When a job moves to `backlog`:
- Its `status` is set to `JobStatus.BACKLOG` in the DB
- `unanswered_fields` lists every field label that went unanswered
- The agent moves immediately to the next job in the queue
- The user can retry a backlog job after adding the missing custom answers

---

## 6. Scaling to Multiple Users & Concurrent Agents

The current implementation is single-user, single-threaded by design (for the demo). Here is how to scale it:

### Multiple Users

The database schema already supports multiple candidates — every `jobs` and `custom_answers` row has a `candidate_id` foreign key. To add a second user, insert a new `Candidate` row and run:

```bash
python main.py --candidate-id 2
```

### Concurrent Agents — Job Queue Infrastructure

Replace the in-process queue with a proper task queue:

```
Candidates submit jobs
        │
        ▼
   Job Queue (Redis + RQ  or  Celery + SQS)
        │
        ├── Worker 1 → processes candidate A's jobs
        ├── Worker 2 → processes candidate B's jobs
        └── Worker 3 → processes candidate C's jobs
```

Each worker runs one `run_job()` call in isolation. Workers can be scaled horizontally — add more containers, more jobs processed in parallel.

**Recommended stack for production:**

| Concern | Solution |
|---|---|
| Job queue | AWS SQS or Redis Streams |
| Workers | Celery workers in Docker containers on ECS/Kubernetes |
| Database | PostgreSQL (already supported via `DATABASE_URL`) |
| Browser | Browserless.io (cloud Playwright) — set `BROWSERLESS_API_KEY` in `.env` |
| HITL | Slack bot or web UI instead of terminal stdin |
| Observability | LangSmith for LLM traces, Datadog for infra metrics |

### Estimated Capacity

| Setup | Throughput |
|---|---|
| 1 worker, 1 browser | ~10–20 applications/hour |
| 10 workers, Browserless | ~100–200 applications/hour |
| 50 workers, Browserless | ~500–1000 applications/hour |

---

## 7. Project Structure

```
ai-job-agent/
├── .env.example                 # credential template
├── main.py                      # entry point
├── requirements.txt
│
├── db/
│   ├── models.py                # SQLAlchemy ORM: Candidate, CustomAnswer, Job
│   └── database.py              # engine, session factory, init_db()
│
├── agent/
│   ├── state.py                 # AgentState TypedDict (shared across all nodes)
│   ├── graph.py                 # LangGraph state machine + run_job()
│   ├── field_mapper.py          # 4-tier field resolution: profile → custom → LLM → HITL
│   └── nodes/
│       ├── resume_tailor.py     # Node 1: LLM tailors resume to JD, writes PDF
│       ├── cover_letter.py      # Node 2: LLM generates cover letter, writes PDF
│       ├── browser_launch.py    # Node 3: Playwright, ATS detection, JD scraping
│       ├── form_filler.py       # Node 4: field discovery + fill via ATS handler
│       └── hitl.py              # Node 5: 30s HITL countdown; Node 6: submit
│
├── ats/
│   ├── base.py                  # Abstract ATSHandler interface
│   ├── factory.py               # get_ats_handler(platform, page) factory
│   ├── workday.py               # Workday handler (data-automation-id selectors)
│   ├── greenhouse.py            # Greenhouse handler (standard HTML forms)
│   └── lever.py                 # Lever handler (/apply URL pattern)
│
└── demo/
    ├── generate_resume.py       # Generates demo PDF resume with reportlab
    └── seed_user.py             # Seeds candidate + custom answers + 6 job URLs
```


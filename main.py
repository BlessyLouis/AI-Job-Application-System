"""
main.py — Entry point for the AI Job Application Agent.

Usage:
    python main.py                   # process all queued jobs for candidate 1
    python main.py --candidate-id 2
    python main.py --job-id 5
"""

from __future__ import annotations

import argparse
import sys

from db.database import get_session, init_db
from db.models import Candidate, Job, JobStatus
from agents.graph import run_job


def get_queued_job_ids(candidate_id: int) -> list[int]:
    with get_session() as session:
        jobs = (
            session.query(Job)
            .filter_by(candidate_id=candidate_id, status=JobStatus.QUEUED)
            .order_by(Job.queued_at.asc())
            .all()
        )
        return [job.id for job in jobs]


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Job Application Agent")
    parser.add_argument("--candidate-id", type=int, default=1)
    parser.add_argument("--job-id",       type=int, default=None)
    args = parser.parse_args()

    init_db()
    candidate_id = args.candidate_id

    # Load candidate name while session is open
    with get_session() as session:
        candidate = session.get(Candidate, candidate_id)
        if not candidate:
            print(f"[main] Candidate ID {candidate_id} not found.")
            print("[main] Run: python -m demo.seed_user")
            sys.exit(1)
        candidate_name  = candidate.full_name
        candidate_email = candidate.email

    print(f"[main] Processing jobs for: {candidate_name} ({candidate_email})")

    # Single job mode
    if args.job_id:
        run_job(args.job_id, candidate_id)
        return

    # Queue mode
    job_ids = get_queued_job_ids(candidate_id)

    if not job_ids:
        print(f"[main] No queued jobs found for candidate {candidate_id}.")
        print("[main] Run: python -m demo.seed_user")
        return

    print(f"[main] Found {len(job_ids)} queued job(s). Starting ...\n")

    results = {"submitted": 0, "failed": 0, "backlog": 0}

    for job_id in job_ids:
        try:
            final_state = run_job(job_id, candidate_id)
            status = final_state.get("status", "unknown")
            results[status] = results.get(status, 0) + 1
        except Exception as e:
            print(f"[main] Unhandled error for job {job_id}: {e}")
            results["failed"] += 1

    print(f"\n{'='*60}")
    print(f"Done! Results for {candidate_name}:")
    print(f"  Submitted : {results['submitted']}")
    print(f"  Backlog   : {results['backlog']}")
    print(f"  Failed    : {results['failed']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

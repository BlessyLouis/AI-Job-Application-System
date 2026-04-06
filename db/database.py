"""
db/database.py
Database engine, session factory, and helper utilities.

Usage:
    from db.database import get_session, init_db

    # Create all tables (run once at startup)
    init_db()

    # Use a session
    with get_session() as session:
        candidate = session.get(Candidate, 1)
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

from db.models import Base

load_dotenv()

# ── Engine ─────────────────────────────────────────────────────────────────────
# Reads DATABASE_URL from .env.
# Defaults to a local SQLite file (great for the demo / local dev).
# Switch to PostgreSQL for production: postgresql://user:pass@host:5432/dbname

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./job_agent.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Required for SQLite when used across threads (e.g. async agents)
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",  # set DB_ECHO=true to log SQL
)

# Enable WAL mode for SQLite — allows concurrent reads while writing
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


# ── Session factory ────────────────────────────────────────────────────────────
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ── Public helpers ─────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create all tables defined in models.py.
    Safe to call multiple times — only creates tables that don't exist yet.
    """
    Base.metadata.create_all(bind=engine)
    print(f"[DB] Tables initialised on: {DATABASE_URL}")


@contextmanager
def get_session() -> Session:
    """
    Context manager that yields a SQLAlchemy session and handles
    commit / rollback / close automatically.

    Example:
        with get_session() as db:
            db.add(some_object)
            # commit happens automatically on exit
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_plain() -> Session:
    """
    Returns a raw session without a context manager.
    Caller is responsible for commit/rollback/close.
    Useful when passing the session into LangGraph node functions.
    """
    return SessionLocal()

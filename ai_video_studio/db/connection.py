"""Prerequisite 2 of 3 for the AWS deployment
(docs/aws-production-architecture.md §5): a connection pool plus idempotent
schema initialization for the two tables that move out of local
files/memory - users (auth/user_store.py's LocalUserStore today) and runs
(web_api/run_registry.py's in-memory RunRegistry today).

No migration framework (Alembic etc.) - deliberately: two small tables,
`CREATE TABLE IF NOT EXISTS` run once at startup is the smallest correct
mechanism, matching this codebase's existing preference for "the simplest
thing that's actually correct" over introducing infrastructure a
two-table schema doesn't need yet."""
from __future__ import annotations

from typing import Optional

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from config import settings
from utils.logger import get_logger

logger = get_logger("db.connection")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    hashed_password TEXT NOT NULL,
    salt TEXT NOT NULL,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    api_keys JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

-- Case-insensitive uniqueness, matching LocalUserStore's own
-- email.strip().lower() normalization convention.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    result JSONB,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_project_stage ON runs (project_id, stage, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs (project_id, started_at DESC);

-- Enforces "one active run per project" (RunRegistry's own documented
-- invariant, SS7.1/SS7.8) atomically at the database level, across every
-- API/worker task at once - not just within one process's dict/lock like
-- the in-memory RunRegistry. A second start_run() for a project that
-- already has a queued/running row violates this index and fails the
-- INSERT, exactly like RunConflictError today.
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_one_active_per_project
    ON runs (project_id)
    WHERE status IN ('queued', 'running');
"""

_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        # make_conninfo (not an f-string) - found necessary during the
        # actual staging deployment: RDS's auto-generated master password
        # (manage_master_user_password=true) can contain characters
        # (spaces, quotes, @, etc.) that corrupt a naively-interpolated
        # "key=value key=value" libpq string - a password containing a
        # space, for example, silently truncates the password= field and
        # authentication then hangs/times out rather than failing loudly.
        # make_conninfo quotes each value correctly regardless of content.
        conninfo = make_conninfo(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
        )
        _pool = ConnectionPool(conninfo, min_size=1, max_size=10, open=True)
        logger.info(f"Database connection pool opened ({settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME})")
    return _pool


def init_schema() -> None:
    """Idempotent - safe to call on every app startup (web_api/__init__.py's
    lifespan), including across multiple API/worker tasks starting
    concurrently (CREATE TABLE/INDEX IF NOT EXISTS is safe under
    concurrent execution; Postgres serializes the DDL)."""
    with get_pool().connection() as conn:
        conn.execute(SCHEMA_SQL)
    logger.info("Database schema verified/initialized (users, runs)")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None

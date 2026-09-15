"""Real integration tests against an actual Postgres instance - not mocked
- because the whole point of prerequisite 2 (docs/aws-production-
architecture.md §5) is a correctness-critical guarantee (atomic "one
active run per project" enforcement via a partial unique index,
idempotent terminal-state transitions) that a mocked connection can't
actually verify.

Skips the entire tests/db/ directory if no test database is reachable,
the same convention this repo already uses for ffmpeg-dependent tests
(tests/test_ffmpeg_executor.py) - rather than failing CI/local runs that
don't have Postgres available.

Point this at a real (disposable) Postgres via TEST_DB_HOST/TEST_DB_PORT/
TEST_DB_NAME/TEST_DB_USER/TEST_DB_PASSWORD env vars, e.g.:
    docker run -d -e POSTGRES_PASSWORD=testpass \\
        -e POSTGRES_DB=ai_video_studio_test -p 15432:5432 postgres:16-alpine
    (defaults below already match this exact command)
"""
import os

import psycopg
import pytest

import db.connection as db_connection
from config import settings

TEST_DB_HOST = os.getenv("TEST_DB_HOST", "localhost")
TEST_DB_PORT = int(os.getenv("TEST_DB_PORT", "15432"))
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "ai_video_studio_test")
TEST_DB_USER = os.getenv("TEST_DB_USER", "postgres")
TEST_DB_PASSWORD = os.getenv("TEST_DB_PASSWORD", "testpass")


def _test_db_available() -> bool:
    try:
        conn = psycopg.connect(
            host=TEST_DB_HOST, port=TEST_DB_PORT, dbname=TEST_DB_NAME,
            user=TEST_DB_USER, password=TEST_DB_PASSWORD, connect_timeout=2,
        )
        conn.close()
        return True
    except Exception:
        return False


_DB_AVAILABLE = _test_db_available()

pytestmark = pytest.mark.skipif(not _DB_AVAILABLE, reason="No test Postgres reachable (see tests/db/conftest.py)")


@pytest.fixture
def db_session(monkeypatch):
    """Points settings/the connection pool at the test database, ensures
    the schema exists, and truncates both tables before each test so
    tests don't see each other's rows."""
    monkeypatch.setattr(settings, "DB_HOST", TEST_DB_HOST)
    monkeypatch.setattr(settings, "DB_PORT", TEST_DB_PORT)
    monkeypatch.setattr(settings, "DB_NAME", TEST_DB_NAME)
    monkeypatch.setattr(settings, "DB_USER", TEST_DB_USER)
    monkeypatch.setattr(settings, "DB_PASSWORD", TEST_DB_PASSWORD)

    db_connection._pool = None  # force a fresh pool bound to the test DB
    db_connection.init_schema()

    with db_connection.get_pool().connection() as conn:
        conn.execute("TRUNCATE TABLE users, runs")

    yield

    db_connection.close_pool()

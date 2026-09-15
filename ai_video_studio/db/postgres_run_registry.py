"""PostgresRunRegistry - the RDS-backed alternative to
web_api/run_registry.py's in-memory RunRegistry, implementing the exact
same public method set (duck-typed, not a formal ABC - RunRegistry itself
isn't one either; this matches the same "same interface, no inheritance
required" convention this codebase already uses for Producer Studio's
deterministic agents, see ARCHITECTURE.md SS8). Swapped in by
web_api/__init__.py::create_app based on whether DB_HOST is configured -
every router's `Depends(get_run_registry)` call site is unchanged, since
both classes expose the same start_run/mark_*/get* methods."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from db.connection import get_pool
from web_api.run_registry import Run, RunConflictError, RunNotFoundError, RunStatus, TERMINAL_STATUSES


def _row_to_run(row: tuple) -> Run:
    run_id, project_id, stage, status, started_at, finished_at, result, error = row
    return Run(
        run_id=run_id,
        project_id=project_id,
        stage=stage,
        status=RunStatus(status),
        started_at=started_at,
        finished_at=finished_at,
        result=result,
        error=error,
    )


_SELECT_COLUMNS = "run_id, project_id, stage, status, started_at, finished_at, result, error"


class PostgresRunRegistry:
    def start_run(self, *, project_id: str, stage: str) -> Run:
        run = Run(
            run_id=str(uuid.uuid4()),
            project_id=project_id,
            stage=stage,
            status=RunStatus.QUEUED,
            started_at=datetime.now(UTC),
        )
        try:
            with get_pool().connection() as conn:
                conn.execute(
                    """
                    INSERT INTO runs (run_id, project_id, stage, status, started_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (run.run_id, run.project_id, run.stage, run.status.value, run.started_at),
                )
        except Exception as exc:
            # The partial unique index (db/connection.py's SCHEMA_SQL,
            # idx_runs_one_active_per_project) is what actually enforces
            # "one active run per project" atomically across every task -
            # a violation surfaces here as a uniqueness constraint error.
            if "idx_runs_one_active_per_project" in str(exc):
                raise RunConflictError(f"Project {project_id} already has an active run") from exc
            raise
        return run

    def mark_running(self, run_id: str) -> None:
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE runs SET status = %s WHERE run_id = %s AND status != ALL(%s)",
                (RunStatus.RUNNING.value, run_id, [s.value for s in TERMINAL_STATUSES]),
            )

    def mark_succeeded(self, run_id: str, *, result: dict = None) -> None:
        self._finish(run_id, status=RunStatus.SUCCEEDED, result=result)

    def mark_failed(self, run_id: str, *, error: str) -> None:
        self._finish(run_id, status=RunStatus.FAILED, error=error)

    def mark_timed_out(self, run_id: str, *, timeout_seconds: float) -> None:
        self._finish(
            run_id, status=RunStatus.TIMED_OUT,
            error=f"Pipeline run exceeded its {timeout_seconds:g}s wall-clock timeout",
        )

    def mark_cancelled(self, run_id: str) -> None:
        self._finish(run_id, status=RunStatus.CANCELLED, error="Run was cancelled before it started executing")

    def _finish(self, run_id: str, *, status: RunStatus, result: dict = None, error: str = None) -> None:
        # Same idempotency guarantee as the in-memory RunRegistry's
        # _finish (web_api/run_registry.py): a late result arriving after
        # a run is already terminal must never overwrite the recorded
        # verdict - enforced here via the `status != ALL(...)` guard
        # directly in the UPDATE, atomically, rather than a separate
        # read-then-write (which would race across tasks). psycopg3 adapts
        # a Python list (not tuple) to a SQL array, which is what
        # `= ANY(%s)` / `!= ALL(%s)` expect - `IN %s` with a tuple, the
        # psycopg2 idiom, is not supported the same way here.
        with get_pool().connection() as conn:
            conn.execute(
                """
                UPDATE runs SET status = %s, finished_at = %s, result = %s, error = %s
                WHERE run_id = %s AND status != ALL(%s)
                """,
                (
                    status.value, datetime.now(UTC),
                    json.dumps(result) if result is not None else None, error,
                    run_id, [s.value for s in TERMINAL_STATUSES],
                ),
            )

    def get(self, run_id: str) -> Run:
        with get_pool().connection() as conn:
            row = conn.execute(f"SELECT {_SELECT_COLUMNS} FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return _row_to_run(row)

    def get_latest_for_project(self, project_id: str, stage: str) -> Run:
        with get_pool().connection() as conn:
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS} FROM runs
                WHERE project_id = %s AND stage = %s
                ORDER BY started_at DESC LIMIT 1
                """,
                (project_id, stage),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(f"No {stage!r} run found for project {project_id}")
        return _row_to_run(row)

    def get_latest_for_project_any_stage(self, project_id: str) -> Run:
        with get_pool().connection() as conn:
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS} FROM runs
                WHERE project_id = %s
                ORDER BY started_at DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(f"No run found for project {project_id}")
        return _row_to_run(row)

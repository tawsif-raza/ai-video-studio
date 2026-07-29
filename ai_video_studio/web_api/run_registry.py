import threading
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Dict, Optional, Tuple

from pydantic import BaseModel


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Run(BaseModel):
    """API-layer bookkeeping for one background pipeline invocation - entirely
    separate from ProjectState (project_manager/project.py). ProjectState
    tracks what has durably happened to a project's data (unchanged, still
    the only source of truth for that); Run tracks the ephemeral fact of one
    HTTP-triggered execution attempt, exactly as WEB_DASHBOARD_ARCHITECTURE.md
    SS7.1 specifies. A project can be re-run, retried, or fail entirely
    without ProjectState ever needing a concept of "in progress" - that
    concern belongs here, not in the core domain model."""

    run_id: str
    project_id: str
    stage: str
    status: RunStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class RunConflictError(Exception):
    """Raised when a project already has an active (queued/running) run."""


class RunNotFoundError(Exception):
    """Raised when a run_id isn't known to this registry."""


class RunRegistry:
    """In-memory Run tracking, deliberately not durable
    (WEB_DASHBOARD_ARCHITECTURE.md SS7.1/SS12): an API process restart loses
    live run state, never outcome state - what actually happened to a
    project is still recorded exactly as v1.0 always did, through
    ProjectManager's own files (project.json, the production package, etc).
    Losing this registry only loses "is a run in flight right now."

    Thread-safe: FastAPI's BackgroundTasks runs a sync callable in a
    worker-thread pool (anyio.to_thread), not on the request's own asyncio
    task, so concurrent requests can mutate this registry from different
    OS threads at once. One instance lives per app, in app.state
    (web_api/__init__.py), not as a process-wide singleton - each
    TestClient(create_app()) in tests gets its own isolated registry."""

    def __init__(self):
        self._runs: Dict[str, Run] = {}
        self._active_by_project: Dict[str, str] = {}
        self._latest_by_project_stage: Dict[Tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def start_run(self, *, project_id: str, stage: str) -> Run:
        with self._lock:
            existing_run_id = self._active_by_project.get(project_id)
            if existing_run_id is not None:
                raise RunConflictError(
                    f"Project {project_id} already has an active run ({existing_run_id})"
                )
            run = Run(
                run_id=str(uuid.uuid4()),
                project_id=project_id,
                stage=stage,
                status=RunStatus.QUEUED,
                started_at=datetime.now(UTC),
            )
            self._runs[run.run_id] = run
            self._active_by_project[project_id] = run.run_id
            # Never cleared on completion, unlike _active_by_project - this is
            # a pure "what was the most recent run for this (project, stage)"
            # pointer, for endpoints like GET .../render/status that look up
            # a run by project_id rather than by run_id.
            self._latest_by_project_stage[(project_id, stage)] = run.run_id
            return run

    def mark_running(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            self._runs[run_id] = run.model_copy(update={"status": RunStatus.RUNNING})

    def mark_succeeded(self, run_id: str, *, result: Optional[dict] = None) -> None:
        self._finish(run_id, status=RunStatus.SUCCEEDED, result=result)

    def mark_failed(self, run_id: str, *, error: str) -> None:
        self._finish(run_id, status=RunStatus.FAILED, error=error)

    def _finish(self, run_id: str, *, status: RunStatus, result: Optional[dict] = None, error: Optional[str] = None) -> None:
        with self._lock:
            run = self._runs[run_id]
            finished = run.model_copy(update={
                "status": status,
                "finished_at": datetime.now(UTC),
                "result": result,
                "error": error,
            })
            self._runs[run_id] = finished
            # Only clear the project's active-run slot once the run reaches a
            # terminal state - this is the one place that enforces "one
            # active run per project" (SS7.1/SS7.8).
            if self._active_by_project.get(finished.project_id) == run_id:
                del self._active_by_project[finished.project_id]

    def get(self, run_id: str) -> Run:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError:
                raise RunNotFoundError(run_id) from None

    def get_latest_for_project(self, project_id: str, stage: str) -> Run:
        """Looks up the most recently started run of a given stage for a
        project, without the caller needing to already know a run_id -
        what GET /projects/{id}/render/status needs (SS_W4). Raises
        RunNotFoundError if no such run has ever been started; the run
        registry is in-memory only, so this is also true after an API
        process restart, exactly like get()."""
        with self._lock:
            run_id = self._latest_by_project_stage.get((project_id, stage))
            if run_id is None:
                raise RunNotFoundError(f"No {stage!r} run found for project {project_id}")
            return self._runs[run_id]

    def get_latest_for_project_any_stage(self, project_id: str) -> Run:
        """Like get_latest_for_project, but without needing to know which
        stage's run is current - what GET /projects/{id}/events needs
        (SS_W6): a project-scoped live-updates stream has to find whichever
        run (director/producer/render/publish) most recently started for
        that project, without this registry hardcoding the set of valid
        stage names anywhere (stage is just a caller-chosen string, as it
        always has been - start_run never validates it either)."""
        with self._lock:
            candidate_ids = [
                run_id for (pid, _stage), run_id in self._latest_by_project_stage.items() if pid == project_id
            ]
            if not candidate_ids:
                raise RunNotFoundError(f"No run found for project {project_id}")
            candidates = [self._runs[run_id] for run_id in candidate_ids]
            return max(candidates, key=lambda r: r.started_at)

import asyncio
from typing import AsyncIterator, Tuple

from web_api.run_registry import Run, RunNotFoundError, RunRegistry, RunStatus

DEFAULT_POLL_INTERVAL_SECONDS = 0.5

_TERMINAL_STATUSES = (RunStatus.SUCCEEDED, RunStatus.FAILED)

# Coarse status -> current_stage label, the same vocabulary
# web_api/routers/render.py and publish.py already use for their
# GET .../status endpoints - kept consistent rather than inventing a
# second one for the stream.
_STAGE_LABELS = {
    RunStatus.QUEUED: "queued",
    RunStatus.RUNNING: "running",
    RunStatus.SUCCEEDED: "completed",
    RunStatus.FAILED: "failed",
}

Event = Tuple[str, dict]


async def run_events(
    run_id: str, run_registry: RunRegistry, *, poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS
) -> AsyncIterator[Event]:
    """Async generator of (event_name, payload) tuples for one run's
    lifecycle - the core of Milestone W6, deliberately separate from SSE
    wire-format serialization (web_api/routers/events.py does that) so it
    can be unit-tested directly against structured data.

    Observes RunRegistry only - never a controller, never a background-task
    runner module (director_runner.py etc). Those keep calling
    mark_running()/mark_succeeded()/mark_failed() exactly as they did
    before this milestone (W2-W5); this generator just polls the same
    already-thread-safe registry.get() every poll_interval and diffs the
    observed status against what it last saw, emitting the event batch for
    each *transition* (never once per poll tick - a run sitting at RUNNING
    across many ticks produces no repeated events). Returns (closing the
    stream) the moment a terminal status is observed, per
    "Completed Runs should automatically close the stream" - including
    immediately, for a run that was already terminal before this generator
    was ever asked to start (a late subscriber gets the outcome, not a
    replay of history the registry never retained in the first place;
    Run itself carries no state-transition log, only current values)."""
    try:
        run_registry.get(run_id)
    except RunNotFoundError:
        return

    last_status = None
    while True:
        run = run_registry.get(run_id)
        if run.status != last_status:
            for event in _events_for(run):
                yield event
            last_status = run.status

        if run.status in _TERMINAL_STATUSES:
            return

        await asyncio.sleep(poll_interval)


def _events_for(run: Run):
    if run.status == RunStatus.RUNNING:
        yield "run_started", {
            "run_id": run.run_id,
            "project_id": run.project_id,
            "type": run.stage,
            "status": run.status.value,
        }
        yield "stage_changed", {"current_stage": _STAGE_LABELS[run.status]}
        yield "progress", {"progress": 50}
    elif run.status == RunStatus.SUCCEEDED:
        yield "progress", {"progress": 100}
        yield "completed", {"status": run.status.value}
    elif run.status == RunStatus.FAILED:
        yield "progress", {"progress": 100}
        yield "failed", {"status": run.status.value, "error": run.error}
    # QUEUED: nothing to report yet beyond the connection itself.

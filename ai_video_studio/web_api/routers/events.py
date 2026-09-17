import json
import uuid
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from project_manager.manager import ProjectManager
from shared_core.contracts.user import UserResponse
from web_api.dependencies import (
    get_optional_current_user,
    get_project_manager,
    get_run_registry,
    get_sse_poll_interval,
)
from web_api.project_authz import get_authorized_project
from web_api.run_registry import RunNotFoundError, RunRegistry
from web_api.sse import run_events

router = APIRouter(tags=["events"])

# text/event-stream must not be buffered by intermediate proxies (nginx's
# default behavior with X-Accel-Buffering unset) or by the browser's own
# HTTP cache - both defeat "live."
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _sse_body(run_id: str, run_registry: RunRegistry, poll_interval: float) -> AsyncIterator[str]:
    """Wire-format serialization only - web_api/sse.py's run_events()
    generates the actual (event_name, payload) sequence; this just formats
    each pair as one SSE message (`event: <name>\\ndata: <json>\\n\\n`,
    the format the browser EventSource API and curl --no-buffer both
    parse)."""
    async for event_name, payload in run_events(run_id, run_registry, poll_interval=poll_interval):
        yield f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    poll_interval: float = Depends(get_sse_poll_interval),
) -> StreamingResponse:
    """Streams one run's lifecycle as Server-Sent Events. Existence is
    checked synchronously up front so an unknown run_id gets a normal 404
    instead of a text/event-stream response that immediately closes -
    the client can tell the two apart without inspecting stream content.

    Multiple clients may call this concurrently for the same run_id: each
    gets its own independent generator instance polling the same
    RunRegistry, so identical updates reach every subscriber with no
    fan-out/broadcast machinery needed. Closing a client connection simply
    stops that one generator being iterated (FastAPI/Starlette cancels it)
    - it has no write access to run_registry or to the background task, so
    it cannot affect run execution either way."""
    run_id_str = str(run_id)
    try:
        run = run_registry.get(run_id_str)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # A run_id is opaque and not itself scoped to a caller, so ownership is
    # authorized via the project it belongs to - same rule as every other
    # project_id-bearing endpoint (web_api/project_authz.py).
    get_authorized_project(project_manager, run.project_id, current_user)

    return StreamingResponse(
        _sse_body(run_id_str, run_registry, poll_interval), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.get("/projects/{project_id}/events")
async def stream_project_events(
    project_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    poll_interval: float = Depends(get_sse_poll_interval),
) -> StreamingResponse:
    """Same stream as GET /runs/{run_id}/events, resolved from a
    project_id instead of an already-known run_id - whichever of
    Director/Producer/Execution/Publishing most recently started for this
    project (RunRegistry.get_latest_for_project_any_stage), since a
    project has at most one active run at a time (W2's conflict rule) but
    may have had runs of different stages sequentially over its lifetime."""
    project_id_str = str(project_id)
    get_authorized_project(project_manager, project_id_str, current_user)

    try:
        run = run_registry.get_latest_for_project_any_stage(project_id_str)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"No run found for project {project_id}")

    return StreamingResponse(
        _sse_body(run.run_id, run_registry, poll_interval), media_type="text/event-stream", headers=_SSE_HEADERS
    )

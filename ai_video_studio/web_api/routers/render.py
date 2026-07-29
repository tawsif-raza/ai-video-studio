import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from starlette.responses import FileResponse

from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from web_api.dependencies import get_execution_controller_factory, get_project_manager, get_run_registry
from web_api.models import RenderRunRequest, RenderStatusResponse, RunAccepted
from web_api.render_runner import run_render_pipeline
from web_api.run_registry import Run, RunConflictError, RunNotFoundError, RunRegistry, RunStatus

router = APIRouter(prefix="/projects/{project_id}/render", tags=["render"])


@router.post("/run", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def run_render(
    project_id: uuid.UUID,
    body: RenderRunRequest,
    background_tasks: BackgroundTasks,
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    controller_factory=Depends(get_execution_controller_factory),
) -> RunAccepted:
    """Wraps ExecutionEngineController.run(project_id=..., options=...)
    exactly as render_app.py does, over the same async Run pattern W2/W3
    established. Two synchronous checks happen here before a Run is even
    created - project existence and EDIT_PLAN_READY eligibility - so an
    ineligible request gets an immediate, clear 400 instead of a 202
    that's only discovered to have failed after polling; the controller's
    own identical EDIT_PLAN_READY check (execution_engine/controller.py
    lines 59-63) remains the authoritative enforcement inside the
    background task regardless, in case project state changes in the
    window between this check and the task actually running."""
    project_id_str = str(project_id)
    try:
        project = project_manager.load_project(project_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if project.status != ProjectState.EDIT_PLAN_READY:
        raise HTTPException(
            status_code=400,
            detail=f"Project {project_id} is at status {project.status.value}, not EDIT_PLAN_READY - "
                   f"run Producer Studio to completion first.",
        )

    try:
        run = run_registry.start_run(project_id=project_id_str, stage="render")
    except RunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    background_tasks.add_task(
        run_render_pipeline,
        run_id=run.run_id,
        project_id=project_id_str,
        project_manager=project_manager,
        run_registry=run_registry,
        controller_factory=controller_factory,
        options=body.to_render_options(),
    )

    return RunAccepted(project_id=project_id_str, run_id=run.run_id, status=run.status)


@router.get("/status", response_model=RenderStatusResponse)
def get_render_status(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
) -> RenderStatusResponse:
    project_id_str = str(project_id)
    try:
        project_manager.load_project(project_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    try:
        run = run_registry.get_latest_for_project(project_id_str, stage="render")
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"No render run found for project {project_id}")

    return _to_status_response(run)


@router.get("/video")
def get_render_video(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> FileResponse:
    """Milestone W8: streams the rendered video Execution Engine already
    produced (rendered_video_path, set only once VIDEO_RENDERED is reached
    - execution_engine/controller.py, save_render_result). No rendering
    logic lives here; this is pure static-file serving of an
    already-finished artifact, the same boundary get_media/upload_media
    already established for other project-owned files.

    Uses Starlette's FileResponse, which has full native HTTP Range
    support built in (single and multi-range, 206 Partial Content, 416 for
    an unsatisfiable range, `Accept-Ranges: bytes`) - no custom range
    parsing is written here, satisfying "support range requests if
    practical" without introducing any new business logic.

    Never returns a filesystem path in the response body - the URL itself
    (/projects/{id}/render/video) is the only thing the frontend ever
    references; the real path only exists server-side, resolved fresh from
    project.rendered_video_path on each request."""
    project_id_str = str(project_id)
    try:
        project = project_manager.load_project(project_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if not project.rendered_video_path:
        raise HTTPException(status_code=404, detail=f"No rendered video available for project {project_id}")

    video_path = Path(project.rendered_video_path)
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail=f"No rendered video available for project {project_id}")

    return FileResponse(video_path, media_type="video/mp4", filename="video.mp4")


def _to_status_response(run: Run) -> RenderStatusResponse:
    """Coarse status -> (current_stage, progress) mapping - the only
    granularity available without the Execution Engine emitting real
    intermediate progress, which this milestone deliberately does not add
    (execution_engine/controller.py runs start-to-finish with no
    progress-reporting hook to observe)."""
    if run.status == RunStatus.QUEUED:
        current_stage, progress = "queued", 0
    elif run.status == RunStatus.RUNNING:
        current_stage, progress = "rendering", 50
    elif run.status == RunStatus.SUCCEEDED:
        current_stage, progress = "completed", 100
    else:
        current_stage, progress = "failed", 100

    return RenderStatusResponse(
        run_id=run.run_id,
        status=run.status,
        current_stage=current_stage,
        progress=progress,
        started_at=run.started_at,
        updated_at=run.finished_at or run.started_at,
        error=run.error,
    )

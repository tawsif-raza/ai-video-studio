import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from web_api.dependencies import get_project_manager, get_publish_controller_factory, get_run_registry
from web_api.models import PublishRunRequest, PublishStatusResponse, RunAccepted
from web_api.publish_runner import run_publish_pipeline
from web_api.run_registry import Run, RunConflictError, RunNotFoundError, RunRegistry, RunStatus

router = APIRouter(prefix="/projects/{project_id}/publish", tags=["publish"])


@router.post("/run", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def run_publish(
    project_id: uuid.UUID,
    body: PublishRunRequest,
    background_tasks: BackgroundTasks,
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    controller_factory=Depends(get_publish_controller_factory),
) -> RunAccepted:
    """Wraps PublishingEngineController.run() exactly as publish_app.py
    does, over the same async Run pattern W2-W4 established.

    Unlike the render/producer eligibility checks, VIDEO_RENDERED here is
    an API-layer-only convenience gate, not a mirror of a real controller
    precondition - PublishingEngineController takes no project_id/project
    at all and enforces nothing about project state itself; readiness
    (including project_status) is deliberately just one more thing
    publishing_engine.preflight.validate_publish_readiness *reports on*,
    by design (project_manager/manager.py's build_publish_readiness_request
    docstring: "never raises even when the project hasn't reached those
    stages yet"). This check exists only for the same fail-fast UX reason
    W4's did: an obviously-premature request gets an immediate 400 instead
    of a 202 whose readiness failure is only visible after polling."""
    project_id_str = str(project_id)
    try:
        project = project_manager.load_project(project_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if project.status != ProjectState.VIDEO_RENDERED:
        raise HTTPException(
            status_code=400,
            detail=f"Project {project_id} is at status {project.status.value}, not VIDEO_RENDERED - "
                   f"render a video before publishing.",
        )

    try:
        run = run_registry.start_run(project_id=project_id_str, stage="publish")
    except RunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    background_tasks.add_task(
        run_publish_pipeline,
        run_id=run.run_id,
        project_id=project_id_str,
        project_manager=project_manager,
        run_registry=run_registry,
        controller_factory=controller_factory,
        platform=body.platform,
        dry_run=body.dry_run,
    )

    return RunAccepted(project_id=project_id_str, run_id=run.run_id, status=run.status)


@router.get("/status", response_model=PublishStatusResponse)
def get_publish_status(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
) -> PublishStatusResponse:
    project_id_str = str(project_id)
    try:
        project = project_manager.load_project(project_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    try:
        run = run_registry.get_latest_for_project(project_id_str, stage="publish")
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"No publish run found for project {project_id}")

    return _to_status_response(run, project.status.value)


def _to_status_response(run: Run, project_state: str) -> PublishStatusResponse:
    """Coarse status -> (current_stage, progress) mapping, same convention
    as web_api/routers/render.py's _to_status_response."""
    if run.status == RunStatus.QUEUED:
        current_stage, progress = "queued", 0
    elif run.status == RunStatus.RUNNING:
        current_stage, progress = "publishing", 50
    elif run.status == RunStatus.SUCCEEDED:
        current_stage, progress = "completed", 100
    else:
        current_stage, progress = "failed", 100

    return PublishStatusResponse(
        run_id=run.run_id,
        status=run.status,
        current_stage=current_stage,
        progress=progress,
        started_at=run.started_at,
        updated_at=run.finished_at or run.started_at,
        error=run.error,
        project_state=project_state,
    )

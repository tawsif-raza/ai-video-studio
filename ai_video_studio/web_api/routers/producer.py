import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from project_manager.manager import ProjectManager
from web_api.dependencies import get_producer_controller_factory, get_project_manager, get_run_registry
from web_api.models import RunAccepted
from web_api.producer_runner import run_producer_pipeline
from web_api.run_registry import RunConflictError, RunRegistry

router = APIRouter(prefix="/projects/{project_id}/producer", tags=["producer"])


@router.post("/run", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def run_producer(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    controller_factory=Depends(get_producer_controller_factory),
) -> RunAccepted:
    """Wraps ProducerStudioController.run(project_id=...) exactly as
    producer_app.py does, over the same async Run pattern W2 established
    for Director Studio. Unlike POST /projects, this operates on an
    existing project_id supplied by the caller, so both failure modes
    that endpoint could only reach synthetically are real here:
    unknown project_id (404) and a second run started while one is
    already active for this project (409, via run_registry's lock)."""
    project_id_str = str(project_id)
    try:
        project_manager.load_project(project_id_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    try:
        run = run_registry.start_run(project_id=project_id_str, stage="producer")
    except RunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    background_tasks.add_task(
        run_producer_pipeline,
        run_id=run.run_id,
        project_id=project_id_str,
        project_manager=project_manager,
        run_registry=run_registry,
        controller_factory=controller_factory,
    )

    return RunAccepted(project_id=project_id_str, run_id=run.run_id, status=run.status)

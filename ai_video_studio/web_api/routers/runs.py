import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from project_manager.manager import ProjectManager
from shared_core.contracts.user import UserResponse
from web_api.dependencies import get_optional_current_user, get_project_manager, get_run_registry
from web_api.project_authz import get_authorized_project
from web_api.run_registry import Run, RunNotFoundError, RunRegistry

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=Run)
def get_run(
    run_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
) -> Run:
    try:
        run = run_registry.get(str(run_id))
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # A run_id is opaque and not itself scoped to a caller, so ownership is
    # authorized via the project it belongs to - same rule as every other
    # project_id-bearing endpoint (web_api/project_authz.py).
    get_authorized_project(project_manager, run.project_id, current_user)
    return run

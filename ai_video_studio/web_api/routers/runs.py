import uuid

from fastapi import APIRouter, Depends, HTTPException

from web_api.dependencies import get_run_registry
from web_api.run_registry import Run, RunNotFoundError, RunRegistry

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}", response_model=Run)
def get_run(run_id: uuid.UUID, run_registry: RunRegistry = Depends(get_run_registry)) -> Run:
    try:
        return run_registry.get(str(run_id))
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

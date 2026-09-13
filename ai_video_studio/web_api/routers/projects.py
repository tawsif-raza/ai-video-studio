import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from project_manager.manager import ProjectManager
from project_manager.project import Project
from shared_core.contracts.asset_manifest import ImportedMediaManifest
from shared_core.contracts.user import UserResponse
from web_api.dependencies import (
    get_director_controller_factory,
    get_llm_client_factory,
    get_optional_current_user,
    get_pipeline_executor,
    get_project_manager,
    get_run_registry,
)
from web_api.director_runner import run_director_pipeline
from web_api.pipeline_executor import PipelineExecutor
from web_api.models import (
    BulkMediaDeleteRequest,
    BulkMediaDeleteResponse,
    CreateProjectRequest,
    MediaCategory,
    MediaDeleteResult,
    MediaUploadResponse,
    RunAccepted,
)
from web_api.run_registry import RunConflictError, RunRegistry

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_authorized_project(
    project_manager: ProjectManager,
    project_id: str,
    current_user: Optional[UserResponse],
) -> Project:
    """Loads a project and verifies ownership authorization.
    If the project is owned by a user:
      - Denies access (404) to unauthenticated requests
      - Denies access (404) to authenticated requests from other users
    If the project has no owner (legacy/unassigned):
      - Permits access
    Returns 404 rather than 403 to prevent probing/enumeration of project existence (IDOR protection).
    """
    owner_id = current_user.id if current_user else None
    try:
        project = project_manager.load_project(project_id, owner_user_id=owner_id)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if project.owner_user_id is not None and (owner_id is None or project.owner_user_id != owner_id):
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    return project


@router.post("", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_project(
    body: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    pipeline_executor: PipelineExecutor = Depends(get_pipeline_executor),
    llm_client_factory=Depends(get_llm_client_factory),
    controller_factory=Depends(get_director_controller_factory),
) -> RunAccepted:
    """Milestone W2: wires project creation to an actual Director Studio run
    (WEB_DASHBOARD_ARCHITECTURE.md SS7.2), superseding W1's bodyless
    bare-creation endpoint. The project is created synchronously here (a
    cheap local file write, not an LLM call) so the 202 response can return
    the real project_id immediately; the LLM-backed pipeline itself runs on
    PipelineExecutor's own bounded, dedicated thread pool - never blocking
    this request, and never able to consume the shared pool ordinary API
    traffic (and GET /health) also depends on (Phase 1.1 P0 fix, Fix 1/2:
    docs/phase1.1-p0-fixes.md). background_tasks.add_task here only ever
    calls pipeline_executor.submit, which itself never blocks - see
    web_api/pipeline_executor.py."""
    owner_id = current_user.id if current_user else None
    project = project_manager.create_project(owner_user_id=owner_id)
    try:
        run = run_registry.start_run(project_id=project.project_id, stage="director")
    except RunConflictError as exc:
        # Cannot actually happen for a project_id that was just minted above,
        # but keeps the registry's one-active-run-per-project invariant
        # enforced the same way for every stage that will use it (W3+).
        raise HTTPException(status_code=409, detail=str(exc))

    background_tasks.add_task(
        pipeline_executor.submit,
        run_id=run.run_id,
        run_registry=run_registry,
        fn=run_director_pipeline,
        project=project,
        project_manager=project_manager,
        idea=body.idea,
        duration=body.duration_seconds,
        tone=body.tone,
        audience=body.audience,
        art_style=body.art_style,
        skip_research=body.skip_research,
        scene_count_mode=body.scene_count_mode,
        scene_count=body.scene_count,
        llm_client_factory=llm_client_factory,
        controller_factory=controller_factory,
    )

    return RunAccepted(project_id=project.project_id, run_id=run.run_id, status=run.status)


@router.get("", response_model=List[Project])
def list_projects(
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> List[Project]:
    if current_user is not None:
        return project_manager.list_projects(owner_user_id=current_user.id)
    return project_manager.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> Project:
    """project_id is typed as uuid.UUID so FastAPI rejects anything that
    isn't a well-formed UUID (422) before it ever reaches ProjectManager,
    which joins project_id directly into a filesystem path
    (ARCHITECTURE.md SS21 item 4's unsanitized-project_id note) - closing
    that path-traversal exposure at the API boundary without changing
    ProjectManager itself."""
    return _get_authorized_project(project_manager, str(project_id), current_user)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> None:
    _get_authorized_project(project_manager, str(project_id), current_user)
    owner_id = current_user.id if current_user else None
    project_manager.delete_project(str(project_id), owner_user_id=owner_id)


@router.post("/{project_id}/media", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_media(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> MediaUploadResponse:
    """One file per call (WEB_DASHBOARD_ARCHITECTURE.md SS7.2) - the
    dashboard batches multiple calls client-side for a multi-file upload.
    Delegates entirely to the new ProjectManager.save_uploaded_media(); this
    handler's only job is HTTP plumbing (load the request body, translate
    ValueError into 400) and project-existence checking."""
    project = _get_authorized_project(project_manager, str(project_id), current_user)

    try:
        saved_path = project_manager.save_uploaded_media(project, file.filename, file.file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    
    # We do not read into memory, so size_bytes might require a stat call.
    # UploadFile provides size (often populated from Content-Length or during spool)
    size_bytes = file.size or 0
    if size_bytes == 0:
        import os
        size_bytes = os.path.getsize(saved_path)

    return MediaUploadResponse(filename=file.filename, path=str(saved_path), size_bytes=size_bytes)


@router.get("/{project_id}/media", response_model=ImportedMediaManifest)
def get_media(
    project_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ImportedMediaManifest:
    """What's currently imported (existing scan_media, unchanged) - the
    dashboard's coverage view before running Producer Studio."""
    project = _get_authorized_project(project_manager, str(project_id), current_user)
    return project_manager.scan_media(project)


@router.delete("/{project_id}/media/{category}/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    project_id: uuid.UUID,
    category: MediaCategory,
    filename: str,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> None:
    """Milestone W10: single-file delete, the counterpart to POST .../media.
    category is a path segment (not inferred from filename) so the URL
    itself says which of the three media subdirectories to look in - the
    same information the dashboard's per-item delete button already has
    from the manifest it's rendering. Delegates entirely to
    ProjectManager.delete_uploaded_media(); this handler's only job is HTTP
    plumbing (project-existence check, ValueError/FileNotFoundError -> 404)."""
    project = _get_authorized_project(project_manager, str(project_id), current_user)

    try:
        project_manager.delete_uploaded_media(project, category.value, filename)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Media file {filename!r} not found in category {category.value!r}"
        )


@router.post("/{project_id}/media/bulk-delete", response_model=BulkMediaDeleteResponse)
def bulk_delete_media(
    project_id: uuid.UUID,
    body: BulkMediaDeleteRequest,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> BulkMediaDeleteResponse:
    """Milestone W10: deletes many media files in one request, reporting
    each item's outcome individually rather than failing the whole batch on
    one missing file - the dashboard's multi-select "delete selected"
    action needs to know exactly which of N files it removed, since a file
    a second browser tab already deleted shouldn't abort the rest of the
    batch. The project-existence check happens once, up front, for the
    whole batch (a project that doesn't exist can't have any media to
    delete); each item's own success/failure is then independent."""
    project = _get_authorized_project(project_manager, str(project_id), current_user)

    results: List[MediaDeleteResult] = []
    for item in body.items:
        try:
            project_manager.delete_uploaded_media(project, item.category.value, item.filename)
            results.append(MediaDeleteResult(category=item.category, filename=item.filename, success=True))
        except FileNotFoundError as exc:
            results.append(
                MediaDeleteResult(category=item.category, filename=item.filename, success=False, error=str(exc))
            )
    return BulkMediaDeleteResponse(results=results)


@router.get("/{project_id}/production-package")
def get_production_package(
    project_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> Dict[str, Any]:
    """Milestone W7.5: exposes the Production Package Director Studio
    already wrote (director_studio + project_manager/package_writer.py),
    read back verbatim via the new ProjectManager.load_production_package -
    no response model is declared beyond a plain dict because the shape is
    inherently heterogeneous (some files are full contract dumps, others
    are the hand-built projections package_writer.py already decided on,
    e.g. scene_plan.json); declaring a stricter schema here would mean
    re-modeling content this router has no business re-deciding the shape
    of. 404 covers both an unknown project and a real one whose Production
    Package doesn't exist yet."""
    project = _get_authorized_project(project_manager, str(project_id), current_user)

    try:
        return project_manager.load_production_package(project)
    except (ValueError, FileNotFoundError):
        raise HTTPException(
            status_code=404, detail=f"Production package not yet generated for project {project_id}"
        )


@router.get("/{project_id}/producer-package")
def get_producer_package(
    project_id: uuid.UUID,
    current_user: Optional[UserResponse] = Depends(get_optional_current_user),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> Dict[str, Any]:
    """Producer Package analog of get_production_package - same
    read-back-only, no-new-modeling approach, wrapping the new
    ProjectManager.load_producer_package."""
    project = _get_authorized_project(project_manager, str(project_id), current_user)

    try:
        return project_manager.load_producer_package(project)
    except (ValueError, FileNotFoundError):
        raise HTTPException(
            status_code=404, detail=f"Producer package not yet generated for project {project_id}"
        )

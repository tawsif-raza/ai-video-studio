import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from project_manager.manager import ProjectManager
from project_manager.project import Project
from shared_core.contracts.asset_manifest import ImportedMediaManifest
from web_api.dependencies import (
    get_director_controller_factory,
    get_llm_client_factory,
    get_project_manager,
    get_run_registry,
)
from web_api.director_runner import run_director_pipeline
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


@router.post("", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_project(
    body: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    project_manager: ProjectManager = Depends(get_project_manager),
    run_registry: RunRegistry = Depends(get_run_registry),
    llm_client_factory=Depends(get_llm_client_factory),
    controller_factory=Depends(get_director_controller_factory),
) -> RunAccepted:
    """Milestone W2: wires project creation to an actual Director Studio run
    (WEB_DASHBOARD_ARCHITECTURE.md SS7.2), superseding W1's bodyless
    bare-creation endpoint. The project is created synchronously here (a
    cheap local file write, not an LLM call) so the 202 response can return
    the real project_id immediately; the LLM-backed pipeline itself runs in
    a background task (run_director_pipeline), never blocking this request."""
    project = project_manager.create_project()
    try:
        run = run_registry.start_run(project_id=project.project_id, stage="director")
    except RunConflictError as exc:
        # Cannot actually happen for a project_id that was just minted above,
        # but keeps the registry's one-active-run-per-project invariant
        # enforced the same way for every stage that will use it (W3+).
        raise HTTPException(status_code=409, detail=str(exc))

    background_tasks.add_task(
        run_director_pipeline,
        run_id=run.run_id,
        project=project,
        project_manager=project_manager,
        run_registry=run_registry,
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
def list_projects(project_manager: ProjectManager = Depends(get_project_manager)) -> List[Project]:
    return project_manager.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> Project:
    """project_id is typed as uuid.UUID so FastAPI rejects anything that
    isn't a well-formed UUID (422) before it ever reaches ProjectManager,
    which joins project_id directly into a filesystem path
    (ARCHITECTURE.md SS21 item 4's unsanitized-project_id note) - closing
    that path-traversal exposure at the API boundary without changing
    ProjectManager itself."""
    try:
        return project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> None:
    try:
        project_manager.delete_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")


@router.post("/{project_id}/media", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> MediaUploadResponse:
    """One file per call (WEB_DASHBOARD_ARCHITECTURE.md SS7.2) - the
    dashboard batches multiple calls client-side for a multi-file upload.
    Delegates entirely to the new ProjectManager.save_uploaded_media(); this
    handler's only job is HTTP plumbing (load the request body, translate
    ValueError into 400) and project-existence checking."""
    try:
        project = project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    content = await file.read()
    try:
        saved_path = project_manager.save_uploaded_media(project, file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MediaUploadResponse(filename=file.filename, path=str(saved_path), size_bytes=len(content))


@router.get("/{project_id}/media", response_model=ImportedMediaManifest)
def get_media(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> ImportedMediaManifest:
    """What's currently imported (existing scan_media, unchanged) - the
    dashboard's coverage view before running Producer Studio."""
    try:
        project = project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project_manager.scan_media(project)


@router.delete("/{project_id}/media/{category}/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    project_id: uuid.UUID,
    category: MediaCategory,
    filename: str,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> None:
    """Milestone W10: single-file delete, the counterpart to POST .../media.
    category is a path segment (not inferred from filename) so the URL
    itself says which of the three media subdirectories to look in - the
    same information the dashboard's per-item delete button already has
    from the manifest it's rendering. Delegates entirely to
    ProjectManager.delete_uploaded_media(); this handler's only job is HTTP
    plumbing (project-existence check, ValueError/FileNotFoundError -> 404)."""
    try:
        project = project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

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
    try:
        project = project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

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
    try:
        project = project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    try:
        return project_manager.load_production_package(project)
    except (ValueError, FileNotFoundError):
        raise HTTPException(
            status_code=404, detail=f"Production package not yet generated for project {project_id}"
        )


@router.get("/{project_id}/producer-package")
def get_producer_package(
    project_id: uuid.UUID,
    project_manager: ProjectManager = Depends(get_project_manager),
) -> Dict[str, Any]:
    """Producer Package analog of get_production_package - same
    read-back-only, no-new-modeling approach, wrapping the new
    ProjectManager.load_producer_package."""
    try:
        project = project_manager.load_project(str(project_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    try:
        return project_manager.load_producer_package(project)
    except (ValueError, FileNotFoundError):
        raise HTTPException(
            status_code=404, detail=f"Producer package not yet generated for project {project_id}"
        )

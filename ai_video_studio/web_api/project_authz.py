from typing import Optional

from fastapi import HTTPException

from project_manager.manager import ProjectManager
from project_manager.project import Project
from shared_core.contracts.user import UserResponse


def get_authorized_project(
    project_manager: ProjectManager,
    project_id: str,
    current_user: Optional[UserResponse],
) -> Project:
    """Loads a project and verifies ownership authorization. Shared by every
    router that operates on a project_id (projects/producer/render/publish/
    events) so "who may touch this project" is enforced identically
    everywhere a project_id crosses the API boundary, rather than each
    router re-deciding it.

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

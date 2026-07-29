import uuid

from tests.web_api.conftest import (
    FailingDirectorController,
    SucceedingDirectorController,
    post_with_controller,
)
from web_api.run_registry import RunStatus


def test_create_project_returns_202_with_project_and_run_id(client, app_):
    response = post_with_controller(client, app_, SucceedingDirectorController)

    assert response.status_code == 202
    body = response.json()
    assert uuid.UUID(body["project_id"])
    assert uuid.UUID(body["run_id"])
    assert body["status"] == RunStatus.QUEUED.value


def test_create_project_precreates_project_before_background_task_runs(client, app_):
    """The project must exist on disk under the id returned by the 202
    response, independent of whether the background pipeline succeeds."""
    response = post_with_controller(client, app_, FailingDirectorController)
    project_id = response.json()["project_id"]

    get_response = client.get(f"/projects/{project_id}")

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "CREATED"


def test_create_project_background_run_reaches_project_via_precreated_delegate(client, app_):
    """The fake controller calls project_manager.create_project() itself
    (mirroring the real controller) - proving _PreCreatedProjectManager
    correctly returns the already-created project instead of allocating a
    second one, and that save_prompt_set really lands on that same project."""
    response = post_with_controller(client, app_, SucceedingDirectorController)
    project_id = response.json()["project_id"]

    projects = client.get("/projects").json()

    assert [p["project_id"] for p in projects] == [project_id]


def test_list_projects_empty_when_none_created(client):
    response = client.get("/projects")

    assert response.status_code == 200
    assert response.json() == []


def test_get_project_unknown_id_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}")

    assert response.status_code == 404


def test_get_project_malformed_id_returns_422(client):
    response = client.get("/projects/not-a-uuid")

    assert response.status_code == 422


def test_get_project_rejects_path_traversal_id(client):
    # Starlette decodes %2F before route matching, so a traversal payload
    # with slashes never matches the single-segment {project_id} route at
    # all (404) - it never reaches load_project. A slash-free malformed
    # value (e.g. "not-a-uuid", tested above) is rejected by the uuid.UUID
    # path type instead (422). Either way, ProjectManager never sees it.
    response = client.get("/projects/..%2F..%2Fetc%2Fpasswd")

    assert response.status_code == 404


def test_delete_project_removes_it(client, app_):
    created = post_with_controller(client, app_, SucceedingDirectorController).json()
    project_id = created["project_id"]

    delete_response = client.delete(f"/projects/{project_id}")
    get_response = client.get(f"/projects/{project_id}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_delete_project_unknown_id_returns_404(client):
    response = client.delete(f"/projects/{uuid.uuid4()}")

    assert response.status_code == 404

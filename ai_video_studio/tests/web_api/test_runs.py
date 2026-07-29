import uuid

from tests.web_api.conftest import (
    CrashingDirectorController,
    FailingDirectorController,
    SucceedingDirectorController,
    post_with_controller,
)
from web_api.run_registry import RunStatus


def test_get_run_unknown_id_returns_404(client):
    response = client.get(f"/runs/{uuid.uuid4()}")

    assert response.status_code == 404


def test_get_run_malformed_id_returns_422(client):
    response = client.get("/runs/not-a-uuid")

    assert response.status_code == 422


def test_successful_run_reaches_succeeded_with_result(client, app_):
    created = post_with_controller(client, app_, SucceedingDirectorController).json()

    run = client.get(f"/runs/{created['run_id']}").json()

    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["project_id"] == created["project_id"]
    assert run["stage"] == "director"
    assert run["finished_at"] is not None
    assert run["error"] is None
    assert "prompt_set_id" in run["result"]


def test_system_exit_from_controller_is_caught_and_marks_run_failed(client, app_):
    """The API boundary requirement: DirectorStudioController raises
    SystemExit(1) on stage failure (director_studio/controller.py); the
    worker must survive it and the run must land in FAILED, not stay stuck
    at RUNNING and not crash the test process."""
    created = post_with_controller(client, app_, FailingDirectorController).json()

    run = client.get(f"/runs/{created['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] is not None
    assert run["finished_at"] is not None

    # The worker is still alive and serving requests after a SystemExit.
    health = client.get("/health")
    assert health.status_code == 200


def test_unexpected_exception_from_controller_is_caught_and_marks_run_failed(client, app_):
    created = post_with_controller(client, app_, CrashingDirectorController).json()

    run = client.get(f"/runs/{created['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] == "boom"


def test_failed_run_does_not_advance_project_state(client, app_):
    created = post_with_controller(client, app_, FailingDirectorController).json()

    project = client.get(f"/projects/{created['project_id']}").json()

    assert project["status"] == "CREATED"

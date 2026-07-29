import uuid

from tests.web_api.conftest import (
    CrashingProducerController,
    FailingProducerController,
    SucceedingProducerController,
    post_producer_run,
)
from web_api.dependencies import get_project_manager
from web_api.run_registry import RunStatus


def test_run_producer_unknown_project_returns_404(client, app_):
    response = post_producer_run(client, app_, SucceedingProducerController, str(uuid.uuid4()))

    assert response.status_code == 404


def test_run_producer_malformed_project_id_returns_422(client, app_):
    response = post_producer_run(client, app_, SucceedingProducerController, "not-a-uuid")

    assert response.status_code == 422


def test_run_producer_returns_202_and_succeeds(client, app_):
    project = get_project_manager().create_project()

    response = post_producer_run(client, app_, SucceedingProducerController, project.project_id)

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == project.project_id
    assert uuid.UUID(body["run_id"])
    assert body["status"] == RunStatus.QUEUED.value

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["stage"] == "producer"
    assert run["result"]["asset_validation"]["is_valid"] is True


def test_run_producer_system_exit_is_caught_and_marks_run_failed(client, app_):
    """The API boundary requirement, mirrored from W2:
    ProducerStudioController also raises SystemExit(1) on a precondition or
    stage failure (producer_studio/controller.py) - the worker must survive
    it, and the run must land in FAILED rather than stay stuck at RUNNING."""
    project = get_project_manager().create_project()

    response = post_producer_run(client, app_, FailingProducerController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] is not None

    assert client.get("/health").status_code == 200


def test_run_producer_unexpected_exception_is_caught_and_marks_run_failed(client, app_):
    project = get_project_manager().create_project()

    response = post_producer_run(client, app_, CrashingProducerController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] == "boom"


def test_run_producer_rejected_with_409_while_a_run_is_already_active(client, app_):
    """Unlike POST /projects (W2), which always mints a brand-new project_id
    and can never self-conflict, this endpoint operates on a caller-supplied
    project_id that can genuinely already have an active run - the real
    scenario run_registry's one-active-run-per-project lock exists for.
    Seeds that state directly on the app's own registry (the same registry
    the router's Depends(get_run_registry) resolves to) rather than racing
    a real in-flight background task, to deterministically exercise the
    router's RunConflictError -> 409 translation."""
    project = get_project_manager().create_project()
    app_.state.run_registry.start_run(project_id=project.project_id, stage="producer")

    response = client.post(f"/projects/{project.project_id}/producer/run")

    assert response.status_code == 409

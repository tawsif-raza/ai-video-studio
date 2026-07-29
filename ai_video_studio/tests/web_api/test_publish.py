import uuid

from tests.web_api.conftest import (
    CrashingPublishController,
    NotReadyPublishController,
    SucceedingPublishController,
    SystemExitPublishController,
    make_video_rendered_project,
    post_publish_run,
)
from web_api.dependencies import get_project_manager
from web_api.run_registry import RunStatus


def test_run_publish_unknown_project_returns_404(client, app_):
    response = post_publish_run(client, app_, SucceedingPublishController, str(uuid.uuid4()))

    assert response.status_code == 404


def test_run_publish_malformed_project_id_returns_422(client, app_):
    response = post_publish_run(client, app_, SucceedingPublishController, "not-a-uuid")

    assert response.status_code == 422


def test_run_publish_rejects_project_not_video_rendered(client, app_):
    project = get_project_manager().create_project()  # freshly created, status CREATED

    response = post_publish_run(client, app_, SucceedingPublishController, project.project_id)

    assert response.status_code == 400


def test_run_publish_returns_202_and_succeeds(client, app_):
    project = make_video_rendered_project(get_project_manager())

    response = post_publish_run(client, app_, SucceedingPublishController, project.project_id)

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == project.project_id
    assert uuid.UUID(body["run_id"])
    assert body["status"] == RunStatus.QUEUED.value

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["stage"] == "publish"
    assert run["result"]["ready_to_publish"] is True
    assert run["result"]["readiness"]["is_valid"] is True
    assert run["result"]["authentication"]["success"] is True


def test_run_publish_defaults_platform_to_youtube(client, app_):
    project = make_video_rendered_project(get_project_manager())

    response = post_publish_run(client, app_, SucceedingPublishController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["result"]["platform"] == "youtube"


def test_run_publish_not_ready_still_succeeds_as_a_reported_outcome(client, app_):
    """Mirrors W3/W4's identical treatment of an invalid asset manifest /
    a failed render: readiness failing is returned data
    (ReadyToPublishResult.ready_to_publish=False), never an exception - the
    publish *request* completed, so the Run is SUCCEEDED, with the verdict
    visible in its result. publish_app.py's own non-zero-but-not-crashing
    exit code already treats this the same way."""
    project = make_video_rendered_project(get_project_manager())

    response = post_publish_run(client, app_, NotReadyPublishController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["ready_to_publish"] is False
    assert run["result"]["readiness"]["is_valid"] is False


def test_run_publish_system_exit_is_caught_and_marks_run_failed(client, app_):
    """Defensive per this milestone's explicit requirement, even though the
    real controller never actually raises SystemExit itself."""
    project = make_video_rendered_project(get_project_manager())

    response = post_publish_run(client, app_, SystemExitPublishController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] is not None
    assert client.get("/health").status_code == 200


def test_run_publish_unexpected_exception_is_caught_and_marks_run_failed(client, app_):
    project = make_video_rendered_project(get_project_manager())

    response = post_publish_run(client, app_, CrashingPublishController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] == "boom"


def test_run_publish_rejected_with_409_while_a_run_is_already_active(client, app_):
    project = make_video_rendered_project(get_project_manager())
    app_.state.run_registry.start_run(project_id=project.project_id, stage="publish")

    response = client.post(f"/projects/{project.project_id}/publish/run", json={})

    assert response.status_code == 409


def test_concurrent_publishes_for_different_projects_both_succeed(client, app_):
    project_manager = get_project_manager()
    project_a = make_video_rendered_project(project_manager)
    project_b = make_video_rendered_project(project_manager)

    response_a = post_publish_run(client, app_, SucceedingPublishController, project_a.project_id)
    response_b = post_publish_run(client, app_, SucceedingPublishController, project_b.project_id)

    assert response_a.status_code == 202
    assert response_b.status_code == 202
    run_a = client.get(f"/runs/{response_a.json()['run_id']}").json()
    run_b = client.get(f"/runs/{response_b.json()['run_id']}").json()
    assert run_a["status"] == RunStatus.SUCCEEDED.value
    assert run_b["status"] == RunStatus.SUCCEEDED.value


def test_publish_status_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/publish/status")

    assert response.status_code == 404


def test_publish_status_no_publish_run_yet_returns_404(client, app_):
    project = make_video_rendered_project(get_project_manager())

    response = client.get(f"/projects/{project.project_id}/publish/status")

    assert response.status_code == 404


def test_publish_status_reports_succeeded_run_with_project_state(client, app_):
    project = make_video_rendered_project(get_project_manager())
    run_id = post_publish_run(client, app_, SucceedingPublishController, project.project_id).json()["run_id"]

    status_response = client.get(f"/projects/{project.project_id}/publish/status")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["run_id"] == run_id
    assert body["status"] == RunStatus.SUCCEEDED.value
    assert body["current_stage"] == "completed"
    assert body["progress"] == 100
    assert body["project_state"] == "VIDEO_RENDERED"
    assert body["error"] is None


def test_publish_status_reports_failed_run_with_error(client, app_):
    project = make_video_rendered_project(get_project_manager())
    run_id = post_publish_run(client, app_, CrashingPublishController, project.project_id).json()["run_id"]

    status_response = client.get(f"/projects/{project.project_id}/publish/status")

    body = status_response.json()
    assert body["run_id"] == run_id
    assert body["status"] == RunStatus.FAILED.value
    assert body["current_stage"] == "failed"
    assert body["error"] == "boom"


def test_successful_publish_never_advances_project_state(client, app_):
    """No PUBLISHED state exists yet (project_manager/project.py) - a
    successful readiness-only publish run must leave project.status
    untouched, exactly as save_publish_report is documented to."""
    project = make_video_rendered_project(get_project_manager())

    post_publish_run(client, app_, SucceedingPublishController, project.project_id)

    reloaded = client.get(f"/projects/{project.project_id}").json()
    assert reloaded["status"] == "VIDEO_RENDERED"

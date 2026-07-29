import uuid

from tests.web_api.conftest import (
    CrashingExecutionController,
    FailedRenderExecutionController,
    RenderErrorExecutionController,
    SucceedingExecutionController,
    SystemExitExecutionController,
    make_edit_plan_ready_project,
    post_render_run,
)
from project_manager.project import ProjectState
from web_api.dependencies import get_project_manager
from web_api.run_registry import RunStatus


def _make_video_rendered_project_with_file(project_manager, video_path):
    video_path.write_bytes(b"0" * 5000)  # not a real mp4 - just needs to exist and stream
    project = project_manager.create_project()
    return project_manager._advance(
        project, status=ProjectState.VIDEO_RENDERED, rendered_video_path=str(video_path)
    )


def test_run_render_unknown_project_returns_404(client, app_):
    response = post_render_run(client, app_, SucceedingExecutionController, str(uuid.uuid4()))

    assert response.status_code == 404


def test_run_render_malformed_project_id_returns_422(client, app_):
    response = post_render_run(client, app_, SucceedingExecutionController, "not-a-uuid")

    assert response.status_code == 422


def test_run_render_rejects_project_not_edit_plan_ready(client, app_):
    project = get_project_manager().create_project()  # freshly created, status CREATED

    response = post_render_run(client, app_, SucceedingExecutionController, project.project_id)

    assert response.status_code == 400


def test_run_render_returns_202_and_succeeds(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())

    response = post_render_run(client, app_, SucceedingExecutionController, project.project_id)

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == project.project_id
    assert uuid.UUID(body["run_id"])
    assert body["status"] == RunStatus.QUEUED.value

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["stage"] == "render"
    assert run["result"]["render"]["success"] is True
    assert run["result"]["validation"]["is_valid"] is True


def test_run_render_with_failed_execution_still_succeeds_as_a_reported_outcome(client, app_):
    """Mirrors W3's identical treatment of an invalid asset manifest: ffmpeg
    exiting non-zero is returned data (RenderResult.success=False), never
    an exception - the render *request* completed, so the Run is SUCCEEDED,
    with the failure visible in its result."""
    project = make_edit_plan_ready_project(get_project_manager())

    response = post_render_run(client, app_, FailedRenderExecutionController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["render"]["success"] is False
    assert "validation" not in run["result"]


def test_run_render_error_is_caught_and_marks_run_failed(client, app_):
    """The controller's real, documented pre-execution failure signal."""
    project = make_edit_plan_ready_project(get_project_manager())

    response = post_render_run(client, app_, RenderErrorExecutionController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert "RenderInputError" in run["error"]


def test_run_render_system_exit_is_caught_and_marks_run_failed(client, app_):
    """Defensive per this milestone's explicit requirement, even though the
    real controller never actually raises SystemExit itself."""
    project = make_edit_plan_ready_project(get_project_manager())

    response = post_render_run(client, app_, SystemExitExecutionController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] is not None
    assert client.get("/health").status_code == 200


def test_run_render_unexpected_exception_is_caught_and_marks_run_failed(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())

    response = post_render_run(client, app_, CrashingExecutionController, project.project_id)
    run = client.get(f"/runs/{response.json()['run_id']}").json()

    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] == "boom"


def test_run_render_rejected_with_409_while_a_run_is_already_active(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())
    app_.state.run_registry.start_run(project_id=project.project_id, stage="render")

    response = client.post(f"/projects/{project.project_id}/render/run", json={})

    assert response.status_code == 409


def test_concurrent_renders_for_different_projects_both_succeed(client, app_):
    project_manager = get_project_manager()
    project_a = make_edit_plan_ready_project(project_manager)
    project_b = make_edit_plan_ready_project(project_manager)

    response_a = post_render_run(client, app_, SucceedingExecutionController, project_a.project_id)
    response_b = post_render_run(client, app_, SucceedingExecutionController, project_b.project_id)

    assert response_a.status_code == 202
    assert response_b.status_code == 202
    run_a = client.get(f"/runs/{response_a.json()['run_id']}").json()
    run_b = client.get(f"/runs/{response_b.json()['run_id']}").json()
    assert run_a["status"] == RunStatus.SUCCEEDED.value
    assert run_b["status"] == RunStatus.SUCCEEDED.value


def test_render_status_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/render/status")

    assert response.status_code == 404


def test_render_status_no_render_run_yet_returns_404(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())

    response = client.get(f"/projects/{project.project_id}/render/status")

    assert response.status_code == 404


def test_render_status_reports_succeeded_run(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())
    run_id = post_render_run(client, app_, SucceedingExecutionController, project.project_id).json()["run_id"]

    status_response = client.get(f"/projects/{project.project_id}/render/status")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["run_id"] == run_id
    assert body["status"] == RunStatus.SUCCEEDED.value
    assert body["current_stage"] == "completed"
    assert body["progress"] == 100
    assert body["started_at"] is not None
    assert body["updated_at"] is not None
    assert body["error"] is None


def test_render_status_reports_failed_run_with_error(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())
    run_id = post_render_run(client, app_, RenderErrorExecutionController, project.project_id).json()["run_id"]

    status_response = client.get(f"/projects/{project.project_id}/render/status")

    body = status_response.json()
    assert body["run_id"] == run_id
    assert body["status"] == RunStatus.FAILED.value
    assert body["current_stage"] == "failed"
    assert body["progress"] == 100
    assert body["error"] is not None


def test_render_video_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/render/video")

    assert response.status_code == 404


def test_render_video_malformed_project_id_returns_422(client):
    response = client.get("/projects/not-a-uuid/render/video")

    assert response.status_code == 422


def test_render_video_no_rendered_video_returns_404(client, app_):
    project = make_edit_plan_ready_project(get_project_manager())  # no rendered_video_path yet

    response = client.get(f"/projects/{project.project_id}/render/video")

    assert response.status_code == 404


def test_render_video_missing_file_on_disk_returns_404(client, app_, tmp_path):
    """rendered_video_path is set but the file itself is gone (moved/deleted
    after the fact) - still a clean 404, not a raw filesystem error."""
    project_manager = get_project_manager()
    project = project_manager.create_project()
    missing_path = tmp_path / "video.mp4"  # never actually written
    project_manager._advance(
        project, status=ProjectState.VIDEO_RENDERED, rendered_video_path=str(missing_path)
    )

    response = client.get(f"/projects/{project.project_id}/render/video")

    assert response.status_code == 404


def test_render_video_streams_the_file_with_correct_content_type(client, app_, tmp_path):
    video_path = tmp_path / "video.mp4"
    project = _make_video_rendered_project_with_file(get_project_manager(), video_path)

    response = client.get(f"/projects/{project.project_id}/render/video")

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b"0" * 5000


def test_render_video_never_leaks_the_filesystem_path(client, app_, tmp_path):
    video_path = tmp_path / "video.mp4"
    project = _make_video_rendered_project_with_file(get_project_manager(), video_path)

    response = client.get(f"/projects/{project.project_id}/render/video")

    assert str(video_path) not in response.headers.get("content-disposition", "")
    for value in response.headers.values():
        assert str(tmp_path) not in value


def test_render_video_supports_range_requests(client, app_, tmp_path):
    video_path = tmp_path / "video.mp4"
    project = _make_video_rendered_project_with_file(get_project_manager(), video_path)

    response = client.get(f"/projects/{project.project_id}/render/video", headers={"Range": "bytes=0-99"})

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-99/5000"
    assert len(response.content) == 100
    assert response.content == b"0" * 100

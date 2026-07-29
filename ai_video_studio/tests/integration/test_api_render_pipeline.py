from fastapi.testclient import TestClient

from execution_engine.controller import ExecutionEngineController
from project_manager.project import ProjectState
from tests.integration.test_render_pipeline import (
    _available_detector,
    _edit_plan_ready_project,
    _fake_failing_executor,
    _fake_successful_executor,
    _passing_prober,
    _unavailable_detector,
)
from web_api import create_app
from web_api.dependencies import get_execution_controller_factory
from web_api.run_registry import RunStatus


def _controller_factory(detector, executor, prober):
    """Curries ExecutionEngineController's constructor kwargs (the same
    injection seam tests/integration/test_render_pipeline.py uses to avoid
    a real ffmpeg binary) into the controller_factory(project_manager)
    shape web_api.render_runner calls. Returns a zero-arg callable, since
    that's what get_execution_controller_factory's own signature is - an
    app.dependency_overrides value must match the overridden dependency's
    own call shape, not the thing it ultimately produces."""
    def factory(project_manager):
        return ExecutionEngineController(project_manager, detector=detector, executor=executor, prober=prober)
    return lambda: factory


def test_full_render_pipeline_via_api_reaches_video_rendered(tmp_path, monkeypatch):
    """End-to-end proof that Milestone W4's async wiring runs the real,
    unmodified ExecutionEngineController exactly as render_app.py does -
    same command building, same executor/prober boundary, same
    ProjectManager persistence - triggered over HTTP instead of argv."""
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    app = create_app()
    app.dependency_overrides[get_execution_controller_factory] = _controller_factory(
        _available_detector, _fake_successful_executor, _passing_prober
    )
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/render/run", json={})
    assert response.status_code == 202
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["render"]["success"] is True
    assert run["result"]["validation"]["is_valid"] is True

    reloaded = client.get(f"/projects/{project.project_id}").json()
    assert reloaded["status"] == ProjectState.VIDEO_RENDERED.value

    status = client.get(f"/projects/{project.project_id}/render/status").json()
    assert status["status"] == RunStatus.SUCCEEDED.value
    assert status["current_stage"] == "completed"
    assert status["progress"] == 100


def test_full_render_pipeline_via_api_with_failed_ffmpeg_does_not_advance_state(tmp_path, monkeypatch):
    """A real ffmpeg failure (RenderResult.success=False) is returned data,
    not an exception - the run SUCCEEDS with the failure visible in its
    result, and the project stays at EDIT_PLAN_READY, never VIDEO_RENDERED."""
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    app = create_app()
    app.dependency_overrides[get_execution_controller_factory] = _controller_factory(
        _available_detector, _fake_failing_executor, _passing_prober
    )
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/render/run", json={})
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["render"]["success"] is False
    assert "validation" not in run["result"]

    reloaded = client.get(f"/projects/{project.project_id}").json()
    assert reloaded["status"] == ProjectState.EDIT_PLAN_READY.value


def test_render_run_via_api_hits_real_render_error_when_ffmpeg_missing(tmp_path, monkeypatch):
    """A real ExecutionEnvironmentError (a RenderError subclass) from the
    real controller when ffmpeg isn't available - the exact non-SystemExit
    failure path the API boundary must translate into a FAILED run."""
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    app = create_app()
    app.dependency_overrides[get_execution_controller_factory] = _controller_factory(
        _unavailable_detector, _fake_successful_executor, _passing_prober
    )
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/render/run", json={})
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.FAILED.value
    assert "ExecutionEnvironmentError" in run["error"]

    assert client.get("/health").status_code == 200

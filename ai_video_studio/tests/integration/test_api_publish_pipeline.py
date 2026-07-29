from fastapi.testclient import TestClient

from project_manager.project import ProjectState
from publishing_engine.controller import PublishingEngineController
from tests.integration.test_render_pipeline import _edit_plan_ready_project
from tests.test_publishing_controller import _FakeCredentialProvider, _FakePlatform
from web_api import create_app
from web_api.dependencies import get_publish_controller_factory
from web_api.run_registry import RunStatus


def _video_rendered_project(tmp_path, monkeypatch):
    """Reuses the real Director+Producer flow (test_render_pipeline.py's
    fixture) so a real publishing_metadata.json exists inside a real
    producer package, then fakes only the one thing that milestone doesn't
    build here - an actual ffmpeg render - by writing a placeholder video
    file and advancing state directly, the same convention
    make_video_rendered_project (tests/web_api/conftest.py) uses for
    router-level tests."""
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    render_dir = manager.get_render_dir(project)
    render_dir.mkdir(parents=True, exist_ok=True)
    video_path = render_dir / "video.mp4"
    video_path.write_bytes(b"fake rendered video bytes")
    project = manager._advance(project, status=ProjectState.VIDEO_RENDERED, rendered_video_path=str(video_path))
    return manager, project


def _controller_factory(platform, credential_provider=None):
    """Curries PublishingEngineController's constructor kwargs (the same
    injection seam tests/test_publishing_controller.py uses) into the
    zero-arg controller_factory() shape web_api.publish_runner calls."""
    def factory():
        return PublishingEngineController(
            platform_resolver=lambda name: (lambda: platform),
            credential_provider=credential_provider or _FakeCredentialProvider(),
        )
    return lambda: factory


def test_full_publish_pipeline_via_api_reports_ready_to_publish(tmp_path, monkeypatch):
    """End-to-end proof that Milestone W5's async wiring runs the real,
    unmodified PublishingEngineController exactly as publish_app.py does -
    same readiness/credential/authentication checks, same
    ProjectManager.save_publish_report persistence - triggered over HTTP
    instead of argv."""
    manager, project = _video_rendered_project(tmp_path, monkeypatch)
    platform = _FakePlatform(credentials_valid=True, auth_success=True)
    app = create_app()
    app.dependency_overrides[get_publish_controller_factory] = _controller_factory(platform)
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/publish/run", json={})
    assert response.status_code == 202
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["ready_to_publish"] is True
    assert run["result"]["readiness"]["is_valid"] is True
    assert run["result"]["authentication"]["success"] is True

    # No PUBLISHED state exists yet (project_manager/project.py) - a
    # successful readiness-only publish run must never advance project
    # status, exactly as save_publish_report is documented to.
    reloaded = client.get(f"/projects/{project.project_id}").json()
    assert reloaded["status"] == ProjectState.VIDEO_RENDERED.value

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    assert (publish_dir / "publish_report.json").exists()

    status = client.get(f"/projects/{project.project_id}/publish/status").json()
    assert status["status"] == RunStatus.SUCCEEDED.value
    assert status["project_state"] == ProjectState.VIDEO_RENDERED.value


def test_full_publish_pipeline_via_api_reports_auth_failure(tmp_path, monkeypatch):
    """A real authentication failure (AuthenticationResult.success=False)
    is returned data, not an exception - the run SUCCEEDS with the failure
    visible in its result, mirroring W3/W4's identical treatment."""
    manager, project = _video_rendered_project(tmp_path, monkeypatch)
    platform = _FakePlatform(credentials_valid=True, auth_success=False, auth_error_type="invalid_credentials")
    app = create_app()
    app.dependency_overrides[get_publish_controller_factory] = _controller_factory(platform)
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/publish/run", json={})
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["ready_to_publish"] is False
    assert run["result"]["authentication"]["success"] is False
    assert run["result"]["authentication"]["error_type"] == "invalid_credentials"


def test_publish_run_via_api_reports_unsupported_platform_without_crashing(tmp_path, monkeypatch):
    """A real, unregistered platform name drives the real controller's own
    internal PublishInputError handling (_check_platform) - no overrides
    at all here (the default get_publish_controller_factory), proving that
    failure is fully absorbed inside the controller and never propagates
    to the API boundary as an exception."""
    manager, project = _video_rendered_project(tmp_path, monkeypatch)
    app = create_app()
    client = TestClient(app)

    response = client.post(
        f"/projects/{project.project_id}/publish/run", json={"platform": "not_a_real_platform"}
    )
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["ready_to_publish"] is False
    assert run["result"]["authentication"]["error_type"] == "unsupported_platform"

    assert client.get("/health").status_code == 200

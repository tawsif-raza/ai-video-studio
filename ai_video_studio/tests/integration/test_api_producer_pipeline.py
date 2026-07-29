from fastapi.testclient import TestClient

from project_manager.project import ProjectState
from tests.integration.test_producer_pipeline import _build_package_ready_project, _write_media
from web_api import create_app
from web_api.run_registry import RunStatus


def test_full_producer_pipeline_via_api_reaches_edit_plan_ready(tmp_path, monkeypatch):
    """End-to-end proof that Milestone W3's async wiring runs the real,
    unmodified ProducerStudioController exactly as producer_app.py does -
    all seven planning stages, same ProjectManager persistence - triggered
    over HTTP instead of argv. None of these agents call an LLM, so this
    test needs no fake LLM client, unlike the Director Studio integration
    tests in test_api_director_pipeline.py."""
    manager, project = _build_package_ready_project(tmp_path, monkeypatch)
    _write_media(
        manager, project,
        images=[("scene_1_shot_1.png", b"0" * 6000), ("scene_1_shot_2.png", b"1" * 6000)],
        audio=[("voice_script.wav", b"2" * 6000)],
    )
    app = create_app()
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/producer/run")
    assert response.status_code == 202
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["asset_validation"]["is_valid"] is True
    assert "timeline" in run["result"]
    assert "subtitles" in run["result"]
    assert "music" in run["result"]
    assert "editing" in run["result"]
    assert "thumbnail" in run["result"]
    assert "publishing" in run["result"]

    reloaded = client.get(f"/projects/{project.project_id}").json()
    assert reloaded["status"] == ProjectState.EDIT_PLAN_READY.value


def test_full_producer_pipeline_via_api_with_incomplete_media_does_not_advance_state(tmp_path, monkeypatch):
    """Asset Validation finding missing media is a reported outcome, not a
    controller failure (producer_studio/controller.py returns normally with
    manifest.is_valid=False) - the run must SUCCEED with that verdict
    visible in its result, matching the "reportable, not exceptional"
    convention this project already applies to render outcomes, and the
    project's status must not advance past PACKAGE_READY."""
    manager, project = _build_package_ready_project(tmp_path, monkeypatch)
    # No media written at all - Asset Validation will find everything missing.
    app = create_app()
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/producer/run")
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.SUCCEEDED.value
    assert run["result"]["asset_validation"]["is_valid"] is False
    assert "timeline" not in run["result"]

    reloaded = client.get(f"/projects/{project.project_id}").json()
    assert reloaded["status"] == ProjectState.PACKAGE_READY.value


def test_producer_run_via_api_on_project_not_ready_hits_real_system_exit(tmp_path, monkeypatch):
    """A project still at CREATED (no Director Studio run at all) drives
    ProducerStudioController to its real precondition check and real
    `raise SystemExit(1)` (producer_studio/controller.py lines 42-49) - the
    exact path the API boundary must survive, with no mocking of the
    failure signal."""
    from config import settings
    from project_manager.manager import ProjectManager

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    app = create_app()
    client = TestClient(app)

    response = client.post(f"/projects/{project.project_id}/producer/run")
    body = response.json()

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == RunStatus.FAILED.value
    assert run["error"] is not None

    assert client.get("/health").status_code == 200

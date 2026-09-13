"""Phase 1.1 P0 fix regression tests (docs/phase1.1-p0-fixes.md, Fix 9):
ProjectManager.reap_orphaned_render_artifacts and its wiring into
web_api's startup lifespan."""
from config import settings
from project_manager.manager import ProjectManager


def _renders_dir(tmp_path, project_id):
    d = tmp_path / "projects" / project_id / "renders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_reap_removes_orphaned_part_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    renders_dir = _renders_dir(tmp_path, project.project_id)
    part_file = renders_dir / "video.part.mp4"
    part_file.write_bytes(b"partial")

    removed = manager.reap_orphaned_render_artifacts()

    assert not part_file.exists()
    assert part_file in removed
    assert any(p.name == "video.part.mp4" for p in removed)


def test_reap_removes_orphaned_stderr_log(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    renders_dir = _renders_dir(tmp_path, project.project_id)
    log_file = renders_dir / "video.stderr.log"
    log_file.write_text("ffmpeg: some error output")

    removed = manager.reap_orphaned_render_artifacts()

    assert not log_file.exists()
    assert any(p.name == "video.stderr.log" for p in removed)


def test_reap_never_touches_a_finished_render(tmp_path, monkeypatch):
    """The one file shape reap_orphaned_render_artifacts must never remove:
    a successfully finished render (no .part/.stderr.log suffix - the exact
    file ffmpeg_executor.execute() only ever produces on verified success)."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    renders_dir = _renders_dir(tmp_path, project.project_id)
    finished_video = renders_dir / "video.mp4"
    finished_video.write_bytes(b"a real finished render")
    report = renders_dir / "render_report.json"
    report.write_text("{}")

    removed = manager.reap_orphaned_render_artifacts()

    assert finished_video.exists()
    assert report.exists()
    assert removed == []


def test_reap_is_safe_with_no_projects_directory_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    assert manager.reap_orphaned_render_artifacts() == []


def test_reap_is_safe_when_a_project_has_no_renders_directory_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    manager.create_project()  # never rendered - no renders/ dir at all

    assert manager.reap_orphaned_render_artifacts() == []


def test_reap_covers_multiple_projects_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project_a = manager.create_project()
    project_b = manager.create_project()
    part_a = _renders_dir(tmp_path, project_a.project_id) / "video.part.mp4"
    part_a.write_bytes(b"x")
    part_b = _renders_dir(tmp_path, project_b.project_id) / "video.part.mov"
    part_b.write_bytes(b"y")

    removed = manager.reap_orphaned_render_artifacts()

    assert not part_a.exists()
    assert not part_b.exists()
    assert len(removed) == 2


def test_web_api_startup_lifespan_runs_the_reaper(tmp_path, monkeypatch):
    """End-to-end proof that the reaper is actually wired into app startup
    (web_api/__init__.py's lifespan), not just unit-tested in isolation -
    requires driving TestClient as a context manager, since Starlette only
    runs lifespan startup/shutdown events that way."""
    from fastapi.testclient import TestClient

    from web_api import create_app

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    orphaned = _renders_dir(tmp_path, project.project_id) / "video.part.mp4"
    orphaned.write_bytes(b"leftover from a hard kill")

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert not orphaned.exists()

from unittest.mock import MagicMock

from config import settings
from project_manager.manager import ProjectManager
from shared_core.contracts.prompt_set import PromptSet
from storage.s3_project_sync import S3ProjectSync
from storage.s3_syncing_project_manager import S3SyncingProjectManager
from tests.storage.fakes import FakeS3Client


def _wrapped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    delegate = ProjectManager()
    s3 = FakeS3Client()
    sync = S3ProjectSync(bucket="test-bucket", s3_client=s3, projects_root=tmp_path / "projects")
    return S3SyncingProjectManager(delegate, sync), delegate, s3


def test_create_project_syncs_up_afterward(tmp_path, monkeypatch):
    wrapped, _, s3 = _wrapped(tmp_path, monkeypatch)

    project = wrapped.create_project()

    assert f"projects/{project.project_id}/project.json" in s3.objects


def test_save_method_syncs_up_the_project_it_was_called_with(tmp_path, monkeypatch):
    wrapped, delegate, s3 = _wrapped(tmp_path, monkeypatch)
    project = delegate.create_project()
    s3.objects.clear()  # only care about what save_prompt_set itself triggers

    wrapped.save_prompt_set(project, PromptSet())

    keys = list(s3.objects.keys())
    assert any(k.startswith(f"projects/{project.project_id}/") for k in keys)


def test_load_project_syncs_down_when_not_cached_locally(tmp_path, monkeypatch):
    wrapped, delegate, s3 = _wrapped(tmp_path, monkeypatch)
    project = delegate.create_project()
    real_project_json = (tmp_path / "projects" / project.project_id / "project.json").read_bytes()
    s3.objects[f"projects/{project.project_id}/project.json"] = real_project_json

    # Simulate a fresh task with empty ephemeral disk - this task has never
    # seen this project before.
    import shutil
    shutil.rmtree(tmp_path / "projects" / project.project_id)

    loaded = wrapped.load_project(project.project_id)

    assert loaded.project_id == project.project_id


def test_load_project_does_not_sync_down_when_already_cached(tmp_path, monkeypatch):
    wrapped, delegate, s3 = _wrapped(tmp_path, monkeypatch)
    project = delegate.create_project()
    s3.download_file = MagicMock(side_effect=AssertionError("should not have synced down - already cached locally"))

    wrapped.load_project(project.project_id)  # must not raise


def test_list_projects_syncs_all_metadata_first(tmp_path, monkeypatch):
    wrapped, delegate, s3 = _wrapped(tmp_path, monkeypatch)
    project = delegate.create_project()
    real_project_json = (tmp_path / "projects" / project.project_id / "project.json").read_bytes()

    # A second "project" that only exists in S3 - as if another API task
    # created it and this task has never touched it.
    s3.objects["projects/other-project-id/project.json"] = real_project_json.replace(
        project.project_id.encode(), b"other-project-id"
    )

    listed_ids = {p.project_id for p in wrapped.list_projects()}

    assert project.project_id in listed_ids
    assert "other-project-id" in listed_ids


def test_a_write_failure_in_s3_does_not_fail_the_underlying_save(tmp_path, monkeypatch):
    """The local write already succeeded - a transient S3 error shouldn't
    turn a successful save into a 500 (see the wrapper's own docstring)."""
    wrapped, delegate, s3 = _wrapped(tmp_path, monkeypatch)
    project = delegate.create_project()

    def _boom(*args, **kwargs):
        raise ConnectionError("simulated S3 outage")

    s3.upload_file = _boom

    result = wrapped.save_prompt_set(project, PromptSet())  # must not raise

    assert result is not None


def test_private_helpers_pass_through_unwrapped(tmp_path, monkeypatch):
    wrapped, delegate, _ = _wrapped(tmp_path, monkeypatch)
    project = delegate.create_project()

    # _project_dir doesn't match any read/write prefix - confirms it's
    # forwarded untouched, not silently swallowed by __getattr__.
    assert wrapped._project_dir(project.project_id) == delegate._project_dir(project.project_id)

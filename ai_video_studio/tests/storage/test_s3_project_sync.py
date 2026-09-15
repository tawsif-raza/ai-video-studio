from tests.storage.fakes import FakeS3Client
from storage.s3_project_sync import S3ProjectSync


def _make_sync(tmp_path):
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    s3 = FakeS3Client()
    sync = S3ProjectSync(bucket="test-bucket", s3_client=s3, projects_root=projects_root)
    return sync, s3, projects_root


def test_sync_up_uploads_every_file_under_the_project(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)
    project_dir = projects_root / "p1"
    (project_dir / "media" / "images").mkdir(parents=True)
    (project_dir / "project.json").write_text('{"id": "p1"}')
    (project_dir / "media" / "images" / "scene_1_shot_1.png").write_bytes(b"fake image bytes")

    uploaded = sync.sync_up("p1")

    assert uploaded == 2
    assert s3.objects["projects/p1/project.json"] == b'{"id": "p1"}'
    assert s3.objects["projects/p1/media/images/scene_1_shot_1.png"] == b"fake image bytes"


def test_sync_up_on_nonexistent_local_dir_is_a_safe_no_op(tmp_path):
    sync, s3, _ = _make_sync(tmp_path)

    assert sync.sync_up("does-not-exist-locally") == 0
    assert s3.objects == {}


def test_download_all_recreates_the_full_directory_tree(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)
    s3.objects["projects/p1/project.json"] = b'{"id": "p1"}'
    s3.objects["projects/p1/media/images/scene_1_shot_1.png"] = b"fake image bytes"

    downloaded = sync.download_all("p1")

    assert downloaded == 2
    assert (projects_root / "p1" / "project.json").read_bytes() == b'{"id": "p1"}'
    assert (projects_root / "p1" / "media" / "images" / "scene_1_shot_1.png").read_bytes() == b"fake image bytes"


def test_download_all_ignores_objects_under_other_projects(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)
    s3.objects["projects/p1/project.json"] = b"p1 data"
    s3.objects["projects/p2/project.json"] = b"p2 data"

    sync.download_all("p1")

    assert (projects_root / "p1" / "project.json").read_bytes() == b"p1 data"
    assert not (projects_root / "p2").exists()


def test_ensure_local_downloads_when_not_cached(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)
    s3.objects["projects/p1/project.json"] = b'{"id": "p1"}'

    sync.ensure_local("p1")

    assert (projects_root / "p1" / "project.json").is_file()


def test_ensure_local_is_a_no_op_when_the_cached_copy_is_still_current(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)
    s3.objects["projects/p1/project.json"] = b"s3 version"
    sync.ensure_local("p1")  # first touch: downloads and records the ETag
    (projects_root / "p1" / "project.json").write_text("locally-modified but S3 unchanged")

    sync.ensure_local("p1")

    # S3's content (and therefore ETag) hasn't changed since the first
    # ensure_local(), so the second call must not re-download - it would
    # have clobbered the local modification above if it had.
    assert (projects_root / "p1" / "project.json").read_text() == "locally-modified but S3 unchanged"


def test_ensure_local_redownloads_when_s3_has_a_newer_version(tmp_path):
    """Regression test for a real staging bug: an API task that only ever
    *created* a project (so it already has a local project.json) kept
    serving that stale copy forever, even after a worker task updated S3
    with the actual pipeline results on a completely separate task's disk.
    ensure_local() must compare against S3's current version, not just
    check "do I have *a* local copy"."""
    sync, s3, projects_root = _make_sync(tmp_path)
    s3.objects["projects/p1/project.json"] = b"created"
    sync.ensure_local("p1")  # e.g. the API task that created the project
    assert (projects_root / "p1" / "project.json").read_bytes() == b"created"

    # A different task (e.g. the worker) updates S3 directly.
    s3.objects["projects/p1/project.json"] = b"package-ready"

    sync.ensure_local("p1")

    assert (projects_root / "p1" / "project.json").read_bytes() == b"package-ready"


def test_ensure_local_is_a_safe_no_op_when_project_does_not_exist_in_s3_yet(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)

    sync.ensure_local("does-not-exist-yet")

    assert not (projects_root / "does-not-exist-yet").exists()


def test_exists_in_s3(tmp_path):
    sync, s3, _ = _make_sync(tmp_path)
    assert sync.exists_in_s3("p1") is False

    s3.objects["projects/p1/project.json"] = b"{}"
    assert sync.exists_in_s3("p1") is True


def test_sync_all_project_metadata_pulls_project_json_for_every_project(tmp_path):
    sync, s3, projects_root = _make_sync(tmp_path)
    s3.objects["projects/p1/project.json"] = b'{"id": "p1"}'
    s3.objects["projects/p1/media/images/x.png"] = b"should NOT be pulled by metadata-only sync"
    s3.objects["projects/p2/project.json"] = b'{"id": "p2"}'

    synced = sync.sync_all_project_metadata()

    assert synced == 2
    assert (projects_root / "p1" / "project.json").read_bytes() == b'{"id": "p1"}'
    assert (projects_root / "p2" / "project.json").read_bytes() == b'{"id": "p2"}'
    assert not (projects_root / "p1" / "media").exists()

from publishing_engine.upload_session_store import FileUploadSessionStore, fingerprint_video_file
from shared_core.contracts.publish import UploadSession


def _session(fingerprint="fp-1", status="in_progress", **overrides):
    defaults = dict(
        platform="youtube",
        session_uri="https://upload.example/session/abc",
        video_path="/tmp/video.mp4",
        content_fingerprint=fingerprint,
        total_bytes=1000,
        bytes_uploaded=200,
        status=status,
    )
    defaults.update(overrides)
    return UploadSession(**defaults)


def test_fingerprint_video_file_is_stable_for_an_unchanged_file(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"some video bytes")

    assert fingerprint_video_file(str(video)) == fingerprint_video_file(str(video))


def test_fingerprint_video_file_changes_when_content_size_changes(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"short")
    fp_before = fingerprint_video_file(str(video))

    video.write_bytes(b"a much longer replacement video payload")
    fp_after = fingerprint_video_file(str(video))

    assert fp_before != fp_after


def test_store_returns_none_when_nothing_persisted_yet(tmp_path):
    store = FileUploadSessionStore(str(tmp_path))

    assert store.load("fp-1") is None


def test_store_round_trips_a_session(tmp_path):
    store = FileUploadSessionStore(str(tmp_path))
    session = _session()

    store.save(session)
    loaded = store.load("fp-1")

    assert loaded is not None
    assert loaded.session_uri == session.session_uri
    assert loaded.bytes_uploaded == 200
    assert loaded.status == "in_progress"


def test_store_creates_the_directory_if_missing(tmp_path):
    nested_dir = tmp_path / "nested" / "publishing"
    store = FileUploadSessionStore(str(nested_dir))

    store.save(_session())

    assert (nested_dir / "upload_session.json").exists()


def test_store_ignores_a_session_recorded_for_a_different_fingerprint(tmp_path):
    store = FileUploadSessionStore(str(tmp_path))
    store.save(_session(fingerprint="fp-old"))

    loaded = store.load("fp-new")  # a re-rendered video - different fingerprint

    assert loaded is None


def test_store_clear_removes_the_persisted_session(tmp_path):
    store = FileUploadSessionStore(str(tmp_path))
    store.save(_session())

    store.clear()

    assert store.load("fp-1") is None


def test_store_clear_is_a_no_op_when_nothing_persisted(tmp_path):
    store = FileUploadSessionStore(str(tmp_path))

    store.clear()  # must not raise


def test_store_load_tolerates_a_corrupted_file(tmp_path):
    store = FileUploadSessionStore(str(tmp_path))
    (tmp_path / "upload_session.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "upload_session.json").write_text("{not valid json")

    assert store.load("fp-1") is None

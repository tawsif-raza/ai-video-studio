from publishing_engine.platforms.youtube import YouTubePlatform
from publishing_engine.upload_session_store import FileUploadSessionStore, fingerprint_video_file
from shared_core.contracts.publish import (
    PlatformCredentials,
    PublishOptions,
    PublishRequest,
    UploadSession,
)
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata


class _FakeGoogleCredentials:
    def __init__(self, **kwargs):
        self.token = None
        self.scopes = kwargs.get("scopes")

    def refresh(self, request):
        self.token = "fake-access-token"


class _FakeResumableUpload:
    """Records exactly how it was invoked and returns a scripted outcome -
    the platform-level tests don't need real chunking, that's already
    covered by test_publishing_youtube_resumable.py."""

    def __init__(self, *, create_result=("https://upload.example/session/new", None), upload_result=(True, 500, "vidNEW", None), query_result=(None, None, None), **kwargs):
        self.create_result = create_result
        self.upload_result = upload_result
        self.query_result = query_result
        self.create_calls = []
        self.upload_calls = []
        self.query_calls = []

    def create_session(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.create_result

    def query_uploaded_bytes(self, **kwargs):
        self.query_calls.append(kwargs)
        return self.query_result

    def upload_file(self, **kwargs):
        self.upload_calls.append(kwargs)
        return self.upload_result


def _valid_credentials():
    return PlatformCredentials(platform="youtube", fields={"client_id": "id", "client_secret": "secret", "refresh_token": "token"})


def _plan(visibility="private"):
    return PublishingPlan(
        canonical=PublishingMetadata(title="T", description="D", category="Education", language="en"),
        youtube=YouTubeMetadata(title="T", description="D", tags=["a", "b"], category="27", default_language="en", playlist="", visibility=visibility),
    )


def _request(tmp_path, video_bytes=b"x" * 500, **option_overrides):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(video_bytes)
    return PublishRequest(
        publishing_plan=_plan(),
        video_path=str(video_path),
        output_dir=str(tmp_path / "publishing"),
        options=PublishOptions(**option_overrides),
    )


def _platform(resumable):
    return YouTubePlatform(
        credentials_factory=lambda **kw: _FakeGoogleCredentials(**kw),
        auth_request_factory=lambda: object(),
        resumable_upload_factory=lambda **kw: resumable,
        session_store_factory=FileUploadSessionStore,
    )


# ---- dry-run safety guard ----


def test_upload_dry_run_makes_no_network_call_and_no_session(tmp_path):
    resumable = _FakeResumableUpload()
    platform = _platform(resumable)

    result = platform.upload(_request(tmp_path, dry_run=True), _valid_credentials())

    assert result.success is True
    assert result.dry_run is True
    assert resumable.create_calls == []
    assert resumable.upload_calls == []
    assert not (tmp_path / "publishing" / "upload_session.json").exists()


# ---- credential failures short-circuit before any upload attempt ----


def test_upload_fails_fast_on_missing_credentials_without_touching_resumable_upload(tmp_path):
    resumable = _FakeResumableUpload()
    platform = _platform(resumable)

    result = platform.upload(_request(tmp_path), PlatformCredentials(platform="youtube", fields={}))

    assert result.success is False
    assert result.error_type == "missing_credentials"
    assert resumable.create_calls == []


# ---- fresh upload, end to end ----


def test_fresh_upload_creates_a_session_and_completes(tmp_path):
    resumable = _FakeResumableUpload(
        create_result=("https://upload.example/session/new", None),
        upload_result=(True, 500, "vidNEW", None),
    )
    platform = _platform(resumable)

    result = platform.upload(_request(tmp_path), _valid_credentials())

    assert result.success is True
    assert result.external_video_id == "vidNEW"
    assert result.bytes_uploaded == 500
    assert result.total_bytes == 500
    assert result.session.status == "completed"
    assert len(resumable.create_calls) == 1
    assert len(resumable.upload_calls) == 1
    assert resumable.upload_calls[0]["resume_from"] == 0


def test_fresh_upload_defaults_to_private_visibility_even_when_plan_says_public(tmp_path):
    resumable = _FakeResumableUpload()
    platform = _platform(resumable)
    request = PublishRequest(
        publishing_plan=_plan(visibility="public"),  # plan says public...
        video_path=str((tmp_path / "video.mp4")),
        output_dir=str(tmp_path / "publishing"),
        options=PublishOptions(),  # ...but no explicit override
    )
    (tmp_path / "video.mp4").write_bytes(b"x" * 500)

    platform.upload(request, _valid_credentials())

    assert resumable.create_calls[0]["status"]["privacyStatus"] == "private"


def test_explicit_visibility_override_is_respected(tmp_path):
    resumable = _FakeResumableUpload()
    platform = _platform(resumable)

    platform.upload(_request(tmp_path, visibility_override="unlisted"), _valid_credentials())

    assert resumable.create_calls[0]["status"]["privacyStatus"] == "unlisted"


def test_fresh_upload_uses_publishing_plan_metadata_for_the_session(tmp_path):
    resumable = _FakeResumableUpload()
    platform = _platform(resumable)

    platform.upload(_request(tmp_path), _valid_credentials())

    snippet = resumable.create_calls[0]["snippet"]
    assert snippet["title"] == "T"
    assert snippet["categoryId"] == "27"
    assert snippet["tags"] == ["a", "b"]


def test_session_create_failure_reports_session_create_failed(tmp_path):
    resumable = _FakeResumableUpload(create_result=(None, "500 server error"))
    platform = _platform(resumable)

    result = platform.upload(_request(tmp_path), _valid_credentials())

    assert result.success is False
    assert result.error_type == "session_create_failed"
    assert resumable.upload_calls == []  # never attempted a chunk with no session


# ---- duplicate-upload avoidance ----


def test_completed_session_is_reused_without_a_new_upload_attempt(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x" * 500)
    output_dir = tmp_path / "publishing"
    store = FileUploadSessionStore(str(output_dir))
    store.save(
        UploadSession(
            platform="youtube", session_uri="https://upload.example/old", video_path=str(video_path),
            content_fingerprint=fingerprint_video_file(str(video_path)), total_bytes=500, bytes_uploaded=500,
            status="completed", external_video_id="vidALREADY",
        )
    )
    resumable = _FakeResumableUpload()
    platform = _platform(resumable)
    request = PublishRequest(publishing_plan=_plan(), video_path=str(video_path), output_dir=str(output_dir), options=PublishOptions())

    result = platform.upload(request, _valid_credentials())

    assert result.success is True
    assert result.external_video_id == "vidALREADY"
    assert resumable.create_calls == []  # no new session
    assert resumable.upload_calls == []  # no bytes re-sent


def test_in_progress_session_resumes_instead_of_starting_a_new_one(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x" * 500)
    output_dir = tmp_path / "publishing"
    store = FileUploadSessionStore(str(output_dir))
    store.save(
        UploadSession(
            platform="youtube", session_uri="https://upload.example/existing", video_path=str(video_path),
            content_fingerprint=fingerprint_video_file(str(video_path)), total_bytes=500, bytes_uploaded=200,
            status="in_progress",
        )
    )
    resumable = _FakeResumableUpload(
        query_result=(200, None, None),  # platform confirms 200 bytes actually received
        upload_result=(True, 500, "vidRESUMED", None),
    )
    platform = _platform(resumable)
    request = PublishRequest(publishing_plan=_plan(), video_path=str(video_path), output_dir=str(output_dir), options=PublishOptions())

    result = platform.upload(request, _valid_credentials())

    assert result.success is True
    assert result.external_video_id == "vidRESUMED"
    assert resumable.create_calls == []  # reused the existing session
    assert resumable.upload_calls[0]["session_uri"] == "https://upload.example/existing"
    assert resumable.upload_calls[0]["resume_from"] == 200


def test_expired_in_progress_session_falls_back_to_a_new_one(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x" * 500)
    output_dir = tmp_path / "publishing"
    store = FileUploadSessionStore(str(output_dir))
    store.save(
        UploadSession(
            platform="youtube", session_uri="https://upload.example/expired", video_path=str(video_path),
            content_fingerprint=fingerprint_video_file(str(video_path)), total_bytes=500, bytes_uploaded=200,
            status="in_progress",
        )
    )
    resumable = _FakeResumableUpload(
        query_result=(None, None, None),  # 404/expired - not resumable
        create_result=("https://upload.example/brand-new", None),
        upload_result=(True, 500, "vidFRESH", None),
    )
    platform = _platform(resumable)
    request = PublishRequest(publishing_plan=_plan(), video_path=str(video_path), output_dir=str(output_dir), options=PublishOptions())

    result = platform.upload(request, _valid_credentials())

    assert result.success is True
    assert len(resumable.create_calls) == 1  # a fresh session was created
    assert resumable.upload_calls[0]["resume_from"] == 0


# ---- interrupted upload persists a resumable session ----


def test_interrupted_upload_persists_in_progress_session_for_later_recovery(tmp_path):
    resumable = _FakeResumableUpload(upload_result=(False, 250, None, "network_error: dropped"))
    platform = _platform(resumable)
    request = _request(tmp_path)

    result = platform.upload(request, _valid_credentials())

    assert result.success is False
    assert result.error_type == "interrupted"
    assert result.bytes_uploaded == 250

    persisted = FileUploadSessionStore(request.output_dir).load(fingerprint_video_file(request.video_path))
    assert persisted is not None
    assert persisted.status == "in_progress"
    assert persisted.bytes_uploaded == 250


def test_upload_reports_progress_via_callback(tmp_path):
    from shared_core.contracts.publish import UploadProgress

    def fake_upload_file(**kwargs):
        cb = kwargs["progress_callback"]
        cb(UploadProgress(bytes_uploaded=250, total_bytes=500, percent_complete=50.0, status="in_progress"))
        cb(UploadProgress(bytes_uploaded=500, total_bytes=500, percent_complete=100.0, status="completed"))
        return True, 500, "vidCB", None

    resumable = _FakeResumableUpload()
    resumable.upload_file = fake_upload_file
    platform = _platform(resumable)
    events = []

    result = platform.upload(_request(tmp_path), _valid_credentials(), progress_callback=events.append)

    assert result.success is True
    assert [e.bytes_uploaded for e in events] == [250, 500]

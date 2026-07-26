"""
Integration test for the upload -> verify -> persist chain: runs the real
YouTubePlatform.upload() and check_status() (only the HTTP layer faked, via
YouTubePlatform's own constructor injection) through the real
publishing_engine.upload_flow.perform_upload(), then persists the result
through the real ProjectManager - proving "a successful HTTP upload does not
automatically imply a successful publish" holds end to end, not just at the
unit level, and that project state is genuinely never touched on disk.
"""

import json

from config import settings
from project_manager.manager import ProjectManager
from publishing_engine.platforms.youtube import YouTubePlatform
from publishing_engine.upload_flow import perform_upload
from shared_core.contracts.publish import PlatformCredentials, PublishOptions, PublishRequest
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata


class _FakeGoogleCredentials:
    def __init__(self, **kwargs):
        self.token = None
        self.scopes = kwargs.get("scopes")

    def refresh(self, request):
        self.token = "fake-access-token"


class _FakeResumableUpload:
    def __init__(self, **kwargs):
        pass

    def create_session(self, **kwargs):
        return "https://upload.example/session/1", None

    def query_uploaded_bytes(self, **kwargs):
        return None, None, None

    def upload_file(self, **kwargs):
        return True, 500, "vidLIVE", None


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


def _plan():
    # PublishOptions has no visibility_override below, so upload()/check_status()
    # both resolve expected visibility to the hard "private" default,
    # deliberately ignoring this plan's "public" - see PublishOptions.
    return PublishingPlan(
        canonical=PublishingMetadata(title="Integration Video", description="D", category="Education", language="en"),
        youtube=YouTubeMetadata(title="Integration Video", description="D", tags=[], category="27", default_language="en", playlist="", visibility="public"),
    )


def _video_response(*, video_id="vidLIVE", found=True, channel_id="channel-abc", privacy_status="private"):
    if not found:
        return _FakeResponse(json_data={"items": []})
    return _FakeResponse(
        json_data={
            "items": [
                {
                    "id": video_id,
                    "snippet": {"title": "Integration Video", "description": "D", "channelId": channel_id},
                    "status": {"privacyStatus": privacy_status, "uploadStatus": "processed"},
                    "contentDetails": {"duration": "PT0S"},
                }
            ]
        }
    )


def _http_get_router(video_response, channel_id="channel-abc"):
    def fn(url, **kwargs):
        if "channels" in url:
            return _FakeResponse(json_data={"items": [{"id": channel_id}]})
        return video_response

    return fn


def test_successful_upload_and_verification_persist_without_touching_project_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    original_project_json = (tmp_path / "projects" / project.project_id / "project.json").read_text()

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x" * 500)
    output_dir = manager.get_publish_dir(project)
    request = PublishRequest(publishing_plan=_plan(), video_path=str(video_path), output_dir=str(output_dir), options=PublishOptions())
    credentials = PlatformCredentials(platform="youtube", fields={"client_id": "id", "client_secret": "s", "refresh_token": "t"})

    platform = YouTubePlatform(
        credentials_factory=lambda **kw: _FakeGoogleCredentials(**kw),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response()),
        resumable_upload_factory=lambda **kw: _FakeResumableUpload(**kw),
        sleep=lambda seconds: None,
    )

    upload_result, verification = perform_upload(platform=platform, request=request, credentials=credentials)

    assert upload_result.success is True
    assert upload_result.external_video_id == "vidLIVE"
    assert verification is not None
    assert verification.is_valid is True  # video really is retrievable, processed, private, matches title/description, owned by us

    manager.save_upload_result(project, upload_result, verification=verification)

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    saved_report = json.loads((publish_dir / "upload_report.json").read_text())
    saved_verification = json.loads((publish_dir / "upload_verification.json").read_text())
    assert saved_report["external_video_id"] == "vidLIVE"
    assert saved_verification["is_valid"] is True
    assert len(saved_verification["checks"]) == 7

    # the whole point: upload success does NOT touch project state
    persisted_project = (tmp_path / "projects" / project.project_id / "project.json").read_text()
    assert persisted_project == original_project_json
    assert json.loads(persisted_project)["status"] == "CREATED"


def test_upload_succeeds_but_video_is_not_yet_retrievable(tmp_path, monkeypatch):
    # The scenario the whole milestone is about: HTTP transfer succeeded,
    # but the platform doesn't (yet) confirm the video is real/retrievable.
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x" * 500)
    output_dir = manager.get_publish_dir(project)
    request = PublishRequest(publishing_plan=_plan(), video_path=str(video_path), output_dir=str(output_dir), options=PublishOptions())
    credentials = PlatformCredentials(platform="youtube", fields={"client_id": "id", "client_secret": "s", "refresh_token": "t"})

    platform = YouTubePlatform(
        credentials_factory=lambda **kw: _FakeGoogleCredentials(**kw),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(found=False)),  # not (yet) retrievable
        resumable_upload_factory=lambda **kw: _FakeResumableUpload(**kw),
        sleep=lambda seconds: None,
    )

    upload_result, verification = perform_upload(platform=platform, request=request, credentials=credentials)

    assert upload_result.success is True  # the bytes were accepted...
    assert verification.is_valid is False  # ...but that alone is not a successful publish

    manager.save_upload_result(project, upload_result, verification=verification)

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    saved_verification = json.loads((publish_dir / "upload_verification.json").read_text())
    assert saved_verification["is_valid"] is False

    persisted_project = json.loads((tmp_path / "projects" / project.project_id / "project.json").read_text())
    assert persisted_project["status"] == "CREATED"


def test_upload_succeeds_but_privacy_status_does_not_match_the_enforced_private_default(tmp_path, monkeypatch):
    # The video was uploaded successfully and IS retrievable, but somehow
    # ended up public (e.g. a channel default override on YouTube's side) -
    # this must still fail verification, proving the check is a genuine
    # confirmation and not just an existence check with a green rubber stamp.
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"x" * 500)
    output_dir = manager.get_publish_dir(project)
    request = PublishRequest(publishing_plan=_plan(), video_path=str(video_path), output_dir=str(output_dir), options=PublishOptions())
    credentials = PlatformCredentials(platform="youtube", fields={"client_id": "id", "client_secret": "s", "refresh_token": "t"})

    platform = YouTubePlatform(
        credentials_factory=lambda **kw: _FakeGoogleCredentials(**kw),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(privacy_status="public")),
        resumable_upload_factory=lambda **kw: _FakeResumableUpload(**kw),
        sleep=lambda seconds: None,
    )

    upload_result, verification = perform_upload(platform=platform, request=request, credentials=credentials)

    assert upload_result.success is True
    assert verification.is_valid is False
    privacy_check = next(c for c in verification.checks if c.name == "privacy_status")
    assert privacy_check.passed is False
    assert privacy_check.expected == "private"
    assert privacy_check.actual == "public"

    manager.save_upload_result(project, upload_result, verification=verification)
    persisted_project = json.loads((tmp_path / "projects" / project.project_id / "project.json").read_text())
    assert persisted_project["status"] == "CREATED"

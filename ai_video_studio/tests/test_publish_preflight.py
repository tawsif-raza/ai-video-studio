import json

from publishing_engine.preflight import validate_publish_readiness
from shared_core.contracts.publish import PublishReadinessRequest

_VALID_METADATA = {
    "canonical": {
        "title": "Test Video",
        "description": "A test video.",
        "keywords": [],
        "hashtags": [],
        "category": "Education",
        "language": "en",
    },
    "youtube": {
        "title": "Test Video",
        "description": "A test video.",
        "tags": [],
        "category": "27",
        "default_language": "en",
        "playlist": "",
        "visibility": "private",
    },
}


def _write_video(tmp_path, name="video.mp4", content=b"fake mp4 bytes"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _write_metadata(tmp_path, data=None, name="publishing_metadata.json"):
    path = tmp_path / name
    path.write_text(json.dumps(_VALID_METADATA if data is None else data))
    return path


def _request(tmp_path, **overrides):
    defaults = dict(
        project_status="VIDEO_RENDERED",
        video_path=str(_write_video(tmp_path)) if "video_path" not in overrides else None,
        publishing_metadata_path=str(_write_metadata(tmp_path)) if "publishing_metadata_path" not in overrides else None,
        platform="youtube",
        output_dir=str(tmp_path / "publishing"),
    )
    defaults.update(overrides)
    return PublishReadinessRequest(**defaults)


def test_valid_publishable_project_passes_every_check(tmp_path):
    report = validate_publish_readiness(_request(tmp_path))

    assert report.is_valid is True
    assert report.platform == "youtube"
    assert all(check.passed for check in report.checks)


def test_project_not_video_rendered_fails(tmp_path):
    report = validate_publish_readiness(_request(tmp_path, project_status="EDIT_PLAN_READY"))

    assert report.is_valid is False
    state_check = next(c for c in report.checks if c.name == "project_state")
    assert state_check.passed is False
    assert state_check.actual == "EDIT_PLAN_READY"


def test_missing_rendered_video_fails(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.mp4")
    report = validate_publish_readiness(_request(tmp_path, video_path=missing_path))

    assert report.is_valid is False
    exists_check = next(c for c in report.checks if c.name == "video_exists")
    assert exists_check.passed is False
    readable_check = next(c for c in report.checks if c.name == "video_readable")
    assert readable_check.passed is False


def test_missing_publishing_metadata_fails(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.json")
    report = validate_publish_readiness(_request(tmp_path, publishing_metadata_path=missing_path))

    assert report.is_valid is False
    metadata_check = next(c for c in report.checks if c.name == "metadata_exists")
    assert metadata_check.passed is False
    # required-field checks also fail gracefully - nothing to read them from
    assert next(c for c in report.checks if c.name == "metadata_title").passed is False


def test_missing_required_metadata_fields_fails(tmp_path):
    incomplete = {
        "canonical": {"title": "", "description": "A test video.", "keywords": [], "hashtags": [], "category": "Education", "language": "en"},
        "youtube": {"title": "Test", "description": "d", "tags": [], "category": "27", "default_language": "en", "playlist": "", "visibility": ""},
    }
    metadata_path = str(_write_metadata(tmp_path, data=incomplete))
    report = validate_publish_readiness(_request(tmp_path, publishing_metadata_path=metadata_path))

    assert report.is_valid is False
    assert next(c for c in report.checks if c.name == "metadata_title").passed is False
    assert next(c for c in report.checks if c.name == "metadata_visibility").passed is False
    # fields that were present should still pass independently
    assert next(c for c in report.checks if c.name == "metadata_description").passed is True


def test_unsupported_platform_fails(tmp_path):
    report = validate_publish_readiness(_request(tmp_path, platform="tiktok"))

    assert report.is_valid is False
    platform_check = next(c for c in report.checks if c.name == "platform_supported")
    assert platform_check.passed is False


def test_missing_publishing_configuration_fails(tmp_path):
    report = validate_publish_readiness(_request(tmp_path, output_dir=""))

    assert report.is_valid is False
    config_check = next(c for c in report.checks if c.name == "publishing_configuration")
    assert config_check.passed is False
    assert "output_dir" in config_check.actual


def test_validate_publish_readiness_never_raises_on_malformed_metadata_json(tmp_path):
    metadata_path = tmp_path / "publishing_metadata.json"
    metadata_path.write_text("{not valid json")

    report = validate_publish_readiness(_request(tmp_path, publishing_metadata_path=str(metadata_path)))

    assert report.is_valid is False
    assert next(c for c in report.checks if c.name == "metadata_exists").passed is False

from publishing_engine.platforms.base import PublishingPlatform
from publishing_engine.upload_flow import perform_upload
from shared_core.contracts.publish import (
    PlatformCredentials,
    PublishOptions,
    PublishRequest,
    PublishResult,
    PublishValidationCheck,
    PublishValidationReport,
)
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata


class _FakePlatform(PublishingPlatform):
    platform_name = "youtube"

    def __init__(self, *, upload_result, check_status_result=None):
        self._upload_result = upload_result
        self._check_status_result = check_status_result
        self.check_status_calls = []

    def validate_credentials(self, credentials):
        raise AssertionError("not exercised by perform_upload")

    def authenticate(self, credentials):
        raise AssertionError("not exercised by perform_upload")

    def upload(self, request, credentials, *, progress_callback=None):
        return self._upload_result

    def check_status(self, request, credentials):
        self.check_status_calls.append(request)
        return self._check_status_result


def _request(*, plan_visibility="private", visibility_override=None):
    plan = PublishingPlan(
        canonical=PublishingMetadata(title="T", description="D", category="Education", language="en"),
        youtube=YouTubeMetadata(title="T", description="D", category="27", default_language="en", playlist="", visibility=plan_visibility),
    )
    return PublishRequest(
        publishing_plan=plan, video_path="/tmp/video.mp4", output_dir="/tmp",
        options=PublishOptions(visibility_override=visibility_override),
    )


def _credentials():
    return PlatformCredentials(platform="youtube", fields={"client_id": "id", "client_secret": "s", "refresh_token": "t"})


def test_successful_upload_is_followed_by_a_verification_call():
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid1", bytes_uploaded=500, total_bytes=500)
    verification = PublishValidationReport(
        is_valid=True, platform="youtube",
        checks=[PublishValidationCheck(name="video_retrievable", passed=True, expected="x", actual="x")],
    )
    platform = _FakePlatform(upload_result=upload_result, check_status_result=verification)

    result, check = perform_upload(platform=platform, request=_request(), credentials=_credentials(), expected_duration_seconds=30.0)

    assert result is upload_result
    assert check is verification
    assert len(platform.check_status_calls) == 1
    verification_request = platform.check_status_calls[0]
    assert verification_request.external_video_id == "vid1"
    assert verification_request.expected_title == "T"
    assert verification_request.expected_description == "D"
    assert verification_request.expected_visibility == "private"
    assert verification_request.expected_duration_seconds == 30.0


def test_failed_upload_skips_verification_entirely():
    upload_result = PublishResult(success=False, platform="youtube", error="boom", error_type="interrupted")
    platform = _FakePlatform(upload_result=upload_result)

    result, check = perform_upload(platform=platform, request=_request(), credentials=_credentials())

    assert result is upload_result
    assert check is None
    assert platform.check_status_calls == []  # never attempted


def test_dry_run_upload_skips_verification_since_there_is_no_real_video():
    upload_result = PublishResult(success=True, dry_run=True, platform="youtube")
    platform = _FakePlatform(upload_result=upload_result)

    result, check = perform_upload(platform=platform, request=_request(), credentials=_credentials())

    assert result.dry_run is True
    assert check is None
    assert platform.check_status_calls == []


def test_verification_failure_is_still_surfaced_even_though_upload_succeeded():
    # This is the whole point of the milestone: success=True on the upload
    # does not mean the caller gets a "successful" verdict without checking.
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid2")
    failing_verification = PublishValidationReport(
        is_valid=False, platform="youtube",
        checks=[PublishValidationCheck(name="video_retrievable", passed=False, expected="x", actual="not found")],
    )
    platform = _FakePlatform(upload_result=upload_result, check_status_result=failing_verification)

    result, check = perform_upload(platform=platform, request=_request(), credentials=_credentials())

    assert result.success is True
    assert check.is_valid is False  # caller must look at BOTH, not just result.success


def test_expected_visibility_ignores_plan_and_uses_the_same_private_default_upload_used():
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid3")
    verification = PublishValidationReport(is_valid=True, platform="youtube", checks=[])
    platform = _FakePlatform(upload_result=upload_result, check_status_result=verification)

    perform_upload(platform=platform, request=_request(plan_visibility="public"), credentials=_credentials())

    assert platform.check_status_calls[0].expected_visibility == "private"


def test_expected_visibility_respects_explicit_override():
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid4")
    verification = PublishValidationReport(is_valid=True, platform="youtube", checks=[])
    platform = _FakePlatform(upload_result=upload_result, check_status_result=verification)

    perform_upload(platform=platform, request=_request(visibility_override="unlisted"), credentials=_credentials())

    assert platform.check_status_calls[0].expected_visibility == "unlisted"


def test_expected_duration_seconds_defaults_to_none_when_not_supplied():
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid5")
    verification = PublishValidationReport(is_valid=True, platform="youtube", checks=[])
    platform = _FakePlatform(upload_result=upload_result, check_status_result=verification)

    perform_upload(platform=platform, request=_request(), credentials=_credentials())

    assert platform.check_status_calls[0].expected_duration_seconds is None

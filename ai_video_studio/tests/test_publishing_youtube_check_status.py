import requests

from publishing_engine.platforms.youtube import YouTubePlatform
from shared_core.contracts.publish import PlatformCredentials, UploadVerificationRequest


class _FakeGoogleCredentials:
    def __init__(self, *, refresh_exception=None, **kwargs):
        self._refresh_exception = refresh_exception
        self.token = None

    def refresh(self, request):
        if self._refresh_exception is not None:
            raise self._refresh_exception
        self.token = "fake-access-token"


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


def _credentials_factory(refresh_exception=None):
    return lambda **kwargs: _FakeGoogleCredentials(refresh_exception=refresh_exception)


def _valid_credentials():
    return PlatformCredentials(platform="youtube", fields={"client_id": "id", "client_secret": "secret", "refresh_token": "rt"})


def _video_response(
    *,
    video_id="vid123",
    title="Expected Title",
    description="Expected description.",
    channel_id="channel-abc",
    privacy_status="private",
    upload_status="processed",
    duration="PT1M30S",
):
    return _FakeResponse(
        json_data={
            "items": [
                {
                    "id": video_id,
                    "snippet": {"title": title, "description": description, "channelId": channel_id},
                    "status": {"privacyStatus": privacy_status, "uploadStatus": upload_status},
                    "contentDetails": {"duration": duration},
                }
            ]
        }
    )


def _channel_response(channel_id="channel-abc"):
    return _FakeResponse(json_data={"items": [{"id": channel_id}]})


def _http_get_router(video_response, channel_response=None):
    """videos.list and channels.list share the same injected http_get - route by endpoint."""

    def fn(url, **kwargs):
        if "channels" in url:
            return channel_response if channel_response is not None else _channel_response()
        return video_response

    return fn


def _request(**overrides):
    defaults = dict(
        external_video_id="vid123",
        expected_title="Expected Title",
        expected_description="Expected description.",
        expected_visibility="private",
        expected_duration_seconds=90.0,
        duration_tolerance_seconds=2.0,
        poll_interval_seconds=0,
        max_poll_attempts=1,
    )
    defaults.update(overrides)
    return UploadVerificationRequest(**defaults)


def test_fully_matching_video_passes_every_check():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response()),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    assert report.is_valid is True
    assert report.external_video_id == "vid123"
    assert {c.name for c in report.checks} == {
        "video_exists", "processing_status", "privacy_status", "duration",
        "title_matches", "description_matches", "channel_ownership",
    }
    assert all(c.passed for c in report.checks)


def test_video_not_found_fails_all_seven_checks_with_consistent_reason():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_FakeResponse(json_data={"items": []})),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    assert report.is_valid is False
    assert len(report.checks) == 7
    assert all(not c.passed for c in report.checks)
    assert report.external_video_id is None


def test_missing_credentials_fails_all_checks_without_any_network_call():
    def _refusing(*a, **k):
        raise AssertionError("must not be called")

    platform = YouTubePlatform(credentials_factory=_refusing, auth_request_factory=_refusing, http_get=_refusing)

    report = platform.check_status(_request(), PlatformCredentials(platform="youtube", fields={}))

    assert report.is_valid is False
    assert len(report.checks) == 7
    assert "missing_credentials" in report.checks[0].actual


def test_processing_status_fails_when_still_uploading_after_polling_budget_exhausted():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(upload_status="uploaded")),  # never reaches "processed"
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(poll_interval_seconds=0, max_poll_attempts=3), _valid_credentials())

    status_check = next(c for c in report.checks if c.name == "processing_status")
    assert status_check.passed is False
    assert status_check.actual == "uploaded"
    assert report.is_valid is False


def test_processing_status_polls_until_terminal_state_is_reached():
    call_count = {"videos": 0}
    responses = [
        _video_response(upload_status="uploaded"),
        _video_response(upload_status="uploaded"),
        _video_response(upload_status="processed"),
    ]

    def http_get(url, **kwargs):
        if "channels" in url:
            return _channel_response()
        response = responses[min(call_count["videos"], len(responses) - 1)]
        call_count["videos"] += 1
        return response

    sleeps = []
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=http_get,
        sleep=sleeps.append,
    )

    report = platform.check_status(_request(poll_interval_seconds=5, max_poll_attempts=5), _valid_credentials())

    status_check = next(c for c in report.checks if c.name == "processing_status")
    assert status_check.passed is True
    assert call_count["videos"] == 3
    assert sleeps == [5, 5]  # slept between the two non-terminal polls, not after the terminal one


def test_privacy_status_mismatch_fails_that_check_only():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(privacy_status="public")),  # expected "private"
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    privacy_check = next(c for c in report.checks if c.name == "privacy_status")
    assert privacy_check.passed is False
    assert privacy_check.actual == "public"
    other_checks = [c for c in report.checks if c.name != "privacy_status"]
    assert all(c.passed for c in other_checks)


def test_duration_outside_tolerance_fails():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(duration="PT2M0S")),  # 120s, expected 90s +/- 2s
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed is False
    assert duration_check.actual == "120.0s"


def test_duration_within_tolerance_passes():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(duration="PT1M31S")),  # 91s, expected 90s +/- 2s
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed is True


def test_duration_check_is_skipped_not_failed_when_no_expected_duration_given():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(duration="PT5M0S")),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(expected_duration_seconds=None), _valid_credentials())

    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed is True
    assert "skipped" in duration_check.expected


def test_title_mismatch_fails_that_check_only():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(title="Wrong Title")),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    title_check = next(c for c in report.checks if c.name == "title_matches")
    assert title_check.passed is False


def test_description_mismatch_fails_that_check_only():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(description="wrong description")),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    description_check = next(c for c in report.checks if c.name == "description_matches")
    assert description_check.passed is False


def test_channel_ownership_fails_when_video_belongs_to_a_different_channel():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get_router(_video_response(channel_id="someone-elses-channel"), _channel_response("channel-abc")),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    ownership_check = next(c for c in report.checks if c.name == "channel_ownership")
    assert ownership_check.passed is False
    assert report.is_valid is False


def test_channel_ownership_check_failure_does_not_block_other_checks():
    def http_get(url, **kwargs):
        if "channels" in url:
            return _FakeResponse(status_code=500, text="server error")
        return _video_response()

    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=http_get,
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    ownership_check = next(c for c in report.checks if c.name == "channel_ownership")
    assert ownership_check.passed is False
    assert "api_error" in ownership_check.actual
    other_checks = [c for c in report.checks if c.name != "channel_ownership"]
    assert all(c.passed for c in other_checks)  # title/description/privacy/duration/processing all still evaluated


def test_network_error_during_video_fetch_fails_all_checks():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError("down")),
        sleep=lambda seconds: None,
    )

    report = platform.check_status(_request(), _valid_credentials())

    assert report.is_valid is False
    assert len(report.checks) == 7
    assert "network_error" in report.checks[0].actual

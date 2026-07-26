import requests
from google.auth.exceptions import RefreshError

from publishing_engine.platforms.youtube import YouTubePlatform
from shared_core.contracts.publish import PlatformCredentials


class _FakeGoogleCredentials:
    def __init__(self, *, refresh_exception=None, resulting_token="fake-access-token", scopes=None):
        self._refresh_exception = refresh_exception
        self._resulting_token = resulting_token
        self.token = None
        self.scopes = scopes

    def refresh(self, request):
        if self._refresh_exception is not None:
            raise self._refresh_exception
        self.token = self._resulting_token


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json_data


def _credentials_factory(refresh_exception=None):
    def factory(**kwargs):
        return _FakeGoogleCredentials(refresh_exception=refresh_exception, scopes=kwargs.get("scopes"))

    return factory


def _http_get(status_code=200, json_data=None, text="", raise_exc=None):
    def fn(*args, **kwargs):
        if raise_exc is not None:
            raise raise_exc
        return _FakeResponse(status_code=status_code, json_data=json_data, text=text)

    return fn


def _valid_credentials():
    return PlatformCredentials(
        platform="youtube", fields={"client_id": "id", "client_secret": "secret", "refresh_token": "rt"}
    )


def _refusing(*args, **kwargs):
    raise AssertionError("must not be called when credential structure validation already failed")


def test_authenticate_fails_fast_on_missing_credentials_without_any_network_call():
    platform = YouTubePlatform(
        credentials_factory=_refusing,
        auth_request_factory=_refusing,
        http_get=_refusing,
    )

    result = platform.authenticate(PlatformCredentials(platform="youtube", fields={}))

    assert result.success is False
    assert result.error_type == "missing_credentials"


def test_authenticate_succeeds_with_valid_credentials_and_working_token():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(status_code=200, json_data={"items": [{"snippet": {"title": "My Channel"}}]}),
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is True
    assert result.platform == "youtube"
    assert result.account_label == "My Channel"
    assert result.error is None
    assert result.error_type is None


def test_authenticate_succeeds_even_when_no_channel_items_returned():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(status_code=200, json_data={"items": []}),
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is True
    assert result.account_label is None


def test_authenticate_handles_expired_refresh_token():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(refresh_exception=RefreshError("invalid_grant")),
        auth_request_factory=lambda: object(),
        http_get=_refusing,
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is False
    assert result.error_type == "expired_token"


def test_authenticate_handles_network_failure_during_token_refresh():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(refresh_exception=requests.exceptions.ConnectionError("no network")),
        auth_request_factory=lambda: object(),
        http_get=_refusing,
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is False
    assert result.error_type == "network_error"


def test_authenticate_handles_network_failure_during_api_call():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(raise_exc=requests.exceptions.Timeout("timed out")),
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is False
    assert result.error_type == "network_error"


def test_authenticate_handles_invalid_credentials_401():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(status_code=401, text="Unauthorized"),
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is False
    assert result.error_type == "invalid_credentials"


def test_authenticate_handles_missing_scopes_403():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(status_code=403, text="insufficientPermissions"),
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is False
    assert result.error_type == "missing_scopes"


def test_authenticate_handles_generic_api_error():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(status_code=500, text="internal error"),
    )

    result = platform.authenticate(_valid_credentials())

    assert result.success is False
    assert result.error_type == "api_error"


def test_authenticate_never_calls_upload_or_check_status():
    platform = YouTubePlatform(
        credentials_factory=_credentials_factory(),
        auth_request_factory=lambda: object(),
        http_get=_http_get(json_data={"items": []}),
    )

    platform.upload = _refusing
    platform.check_status = _refusing

    result = platform.authenticate(_valid_credentials())

    assert result.success is True

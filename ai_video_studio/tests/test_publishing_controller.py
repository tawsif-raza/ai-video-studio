from publishing_engine.controller import PublishingEngineController
from publishing_engine.credentials import CredentialProvider
from publishing_engine.platforms.base import PublishingPlatform
from shared_core.contracts.publish import (
    AuthenticationResult,
    PlatformCredentials,
    PublishReadinessRequest,
    PublishValidationCheck,
    PublishValidationReport,
)
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata


def _valid_plan() -> PublishingPlan:
    return PublishingPlan(
        canonical=PublishingMetadata(title="T", description="D", category="Education", language="en"),
        youtube=YouTubeMetadata(
            title="T", description="D", category="27", default_language="en", playlist="", visibility="private"
        ),
    )


def _ready_request(tmp_path) -> PublishReadinessRequest:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake mp4 bytes")
    metadata_path = tmp_path / "publishing_metadata.json"
    metadata_path.write_text(_valid_plan().model_dump_json())
    return PublishReadinessRequest(
        project_status="VIDEO_RENDERED",
        video_path=str(video_path),
        publishing_metadata_path=str(metadata_path),
        platform="youtube",
        output_dir=str(tmp_path / "publishing"),
    )


class _FakeCredentialProvider(CredentialProvider):
    def __init__(self, fields=None):
        self.fields = fields if fields is not None else {"client_id": "id", "client_secret": "secret", "refresh_token": "token"}
        self.load_calls = []

    def load(self, platform: str) -> PlatformCredentials:
        self.load_calls.append(platform)
        return PlatformCredentials(platform=platform, fields=self.fields)


class _FakePlatform(PublishingPlatform):
    platform_name = "youtube"

    def __init__(self, *, credentials_valid=True, auth_success=True, auth_error_type="api_error"):
        self._credentials_valid = credentials_valid
        self._auth_success = auth_success
        self._auth_error_type = auth_error_type
        self.authenticate_calls = 0

    def validate_credentials(self, credentials):
        return PublishValidationReport(
            is_valid=self._credentials_valid,
            platform=self.platform_name,
            checks=[
                PublishValidationCheck(
                    name="credential_client_id", passed=self._credentials_valid, expected="present", actual="x"
                )
            ],
        )

    def authenticate(self, credentials):
        self.authenticate_calls += 1
        if self._auth_success:
            return AuthenticationResult(success=True, platform=self.platform_name, account_label="My Channel")
        return AuthenticationResult(
            success=False, platform=self.platform_name, error="boom", error_type=self._auth_error_type
        )

    def upload(self, request, credentials, *, progress_callback=None):
        raise AssertionError("upload() must never be called by the controller (Milestone P5)")

    def check_status(self, request, credentials):
        raise AssertionError("check_status() must never be called by the controller (Milestone P5)")


def _controller(platform, *, credential_provider=None):
    return PublishingEngineController(
        platform_resolver=lambda name: (lambda: platform),
        credential_provider=credential_provider or _FakeCredentialProvider(),
    )


def test_controller_ready_when_readiness_credentials_and_auth_all_pass(tmp_path):
    platform = _FakePlatform()
    controller = _controller(platform)

    result = controller.run(readiness_request=_ready_request(tmp_path), publishing_plan=_valid_plan(), dry_run=True)

    assert result.readiness.is_valid is True
    assert result.credentials.is_valid is True
    assert result.authentication.success is True
    assert result.ready_to_publish is True
    assert result.request is not None
    assert result.request.options.dry_run is True
    assert platform.authenticate_calls == 1


def test_controller_not_ready_when_readiness_fails(tmp_path):
    platform = _FakePlatform()
    controller = _controller(platform)
    request = _ready_request(tmp_path).model_copy(update={"project_status": "EDIT_PLAN_READY"})

    result = controller.run(readiness_request=request, publishing_plan=_valid_plan())

    assert result.readiness.is_valid is False
    assert result.ready_to_publish is False
    assert result.request is None
    # readiness failing doesn't prevent the platform/credential/auth checks from still running
    assert platform.authenticate_calls == 1


def test_controller_skips_authentication_when_credentials_invalid(tmp_path):
    platform = _FakePlatform(credentials_valid=False)
    controller = _controller(platform)

    result = controller.run(readiness_request=_ready_request(tmp_path), publishing_plan=_valid_plan())

    assert result.credentials.is_valid is False
    assert result.authentication.success is False
    assert result.authentication.error_type == "missing_credentials"
    assert result.ready_to_publish is False
    assert platform.authenticate_calls == 0  # never even attempted


def test_controller_not_ready_when_authentication_fails(tmp_path):
    platform = _FakePlatform(auth_success=False, auth_error_type="expired_token")
    controller = _controller(platform)

    result = controller.run(readiness_request=_ready_request(tmp_path), publishing_plan=_valid_plan())

    assert result.credentials.is_valid is True
    assert result.authentication.success is False
    assert result.authentication.error_type == "expired_token"
    assert result.ready_to_publish is False
    assert result.request is None


def test_controller_handles_unsupported_platform_without_loading_credentials(tmp_path):
    provider = _FakeCredentialProvider()
    controller = PublishingEngineController(credential_provider=provider)  # real registry, "tiktok" unregistered
    request = _ready_request(tmp_path).model_copy(update={"platform": "tiktok"})

    result = controller.run(readiness_request=request, publishing_plan=_valid_plan())

    assert result.ready_to_publish is False
    assert result.credentials.is_valid is False
    assert result.authentication.error_type == "unsupported_platform"
    assert provider.load_calls == []  # credentials never loaded for an unregistered platform


def test_controller_loads_credentials_through_the_injected_provider(tmp_path):
    platform = _FakePlatform()
    provider = _FakeCredentialProvider()
    controller = _controller(platform, credential_provider=provider)

    controller.run(readiness_request=_ready_request(tmp_path))

    assert provider.load_calls == ["youtube"]


def test_controller_caches_authentication_across_repeated_calls(tmp_path):
    platform = _FakePlatform()
    controller = _controller(platform)
    request = _ready_request(tmp_path)

    controller.run(readiness_request=request)
    controller.run(readiness_request=request)

    assert platform.authenticate_calls == 1  # second call served from the cache


def test_context_has_no_request_when_no_publishing_plan_supplied(tmp_path):
    platform = _FakePlatform()
    controller = _controller(platform)

    result = controller.run(readiness_request=_ready_request(tmp_path), publishing_plan=None)

    assert result.ready_to_publish is True
    assert result.request is None


def test_dry_run_defaults_true_and_threads_through(tmp_path):
    platform = _FakePlatform()
    controller = _controller(platform)

    result = controller.run(readiness_request=_ready_request(tmp_path), publishing_plan=_valid_plan())

    assert result.dry_run is True

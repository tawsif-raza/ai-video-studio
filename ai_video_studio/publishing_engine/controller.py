"""
Milestone P5 (ARCHITECTURE.md SS24): PublishingEngineController wires
together every existing Publishing Engine component - readiness validation
(preflight.py), platform resolution (platforms/registry.py), credential
sourcing (credentials.py), and real authentication (each platform adapter's
authenticate(), rate-limited/cached via auth_cache.py) - into one
ReadyToPublishResult.

It never uploads, never submits metadata, never manages thumbnails or
playlists, never touches project state, and never writes a report to disk.
Those all remain later milestones' jobs. It still never imports
project_manager (Milestone P2's boundary, unchanged) - it takes typed inputs
from its caller (publish_app.py), exactly like preflight.validate_publish_readiness
does.

Every dependency is injectable, mirroring ExecutionEngineController's
pattern (detector=detect_ffmpeg, executor=execute, prober=probe).
"""

from typing import Callable, Optional, Tuple, Type

from publishing_engine.auth_cache import AuthenticationCache, fingerprint_credentials
from publishing_engine.credentials import CredentialProvider, EnvCredentialProvider
from publishing_engine.errors import PublishInputError
from publishing_engine.platforms.base import PublishingPlatform
from publishing_engine.platforms.registry import resolve_platform
from publishing_engine.preflight import validate_publish_readiness
from shared_core.contracts.publish import (
    AuthenticationResult,
    PlatformCredentials,
    PublishOptions,
    PublishReadinessRequest,
    PublishRequest,
    PublishValidationCheck,
    PublishValidationReport,
    ReadyToPublishResult,
)
from shared_core.contracts.publishing_metadata import PublishingPlan


class PublishingEngineController:
    def __init__(
        self,
        *,
        platform_resolver: Callable[[str], Type[PublishingPlatform]] = resolve_platform,
        readiness_check: Callable[[PublishReadinessRequest], PublishValidationReport] = validate_publish_readiness,
        credential_provider: Optional[CredentialProvider] = None,
        auth_cache: Optional[AuthenticationCache] = None,
    ):
        self._resolve_platform = platform_resolver
        self._check_readiness = readiness_check
        self._credential_provider = credential_provider if credential_provider is not None else EnvCredentialProvider()
        self._auth_cache = auth_cache if auth_cache is not None else AuthenticationCache()

    def run(
        self,
        *,
        readiness_request: PublishReadinessRequest,
        publishing_plan: Optional[PublishingPlan] = None,
        dry_run: bool = True,
    ) -> ReadyToPublishResult:
        readiness = self._check_readiness(readiness_request)
        credential_report, authentication = self._check_platform(readiness_request.platform)

        ready = readiness.is_valid and credential_report.is_valid and authentication.success

        request = None
        if ready and publishing_plan is not None:
            request = PublishRequest(
                publishing_plan=publishing_plan,
                video_path=readiness_request.video_path,
                output_dir=readiness_request.output_dir,
                options=PublishOptions(platform=readiness_request.platform, dry_run=dry_run),
            )

        return ReadyToPublishResult(
            platform=readiness_request.platform,
            dry_run=dry_run,
            readiness=readiness,
            credentials=credential_report,
            authentication=authentication,
            ready_to_publish=ready,
            request=request,
        )

    def _check_platform(self, platform_name: str) -> Tuple[PublishValidationReport, AuthenticationResult]:
        """Resolves the platform through the registry, loads credentials
        through the provider, validates their structure, and - only if that
        structure is valid - authenticates (rate-limited/cached). Never
        loads credentials for a platform that isn't even registered."""
        try:
            platform_cls = self._resolve_platform(platform_name)
        except PublishInputError as e:
            unsupported_report = PublishValidationReport(
                is_valid=False,
                platform=platform_name,
                checks=[
                    PublishValidationCheck(
                        name="platform_supported", passed=False, expected="registered platform", actual=str(e)
                    )
                ],
            )
            unsupported_auth = AuthenticationResult(
                success=False, platform=platform_name, error=str(e), error_type="unsupported_platform"
            )
            return unsupported_report, unsupported_auth

        platform_instance = platform_cls()
        credentials = self._credential_provider.load(platform_name)
        credential_report = platform_instance.validate_credentials(credentials)
        authentication = self._authenticate(platform_instance, credentials, credential_report)
        return credential_report, authentication

    def _authenticate(
        self,
        platform_instance: PublishingPlatform,
        credentials: PlatformCredentials,
        credential_report: PublishValidationReport,
    ) -> AuthenticationResult:
        if not credential_report.is_valid:
            return AuthenticationResult(
                success=False,
                platform=platform_instance.platform_name,
                error="credential structure invalid - authentication skipped",
                error_type="missing_credentials",
            )
        key = (platform_instance.platform_name, fingerprint_credentials(credentials))
        return self._auth_cache.get_or_authenticate(key, lambda: platform_instance.authenticate(credentials))

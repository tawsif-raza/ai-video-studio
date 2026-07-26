from abc import ABC, abstractmethod
from typing import Callable, Optional

from shared_core.contracts.publish import (
    AuthenticationResult,
    PlatformCredentials,
    PublishRequest,
    PublishResult,
    PublishValidationReport,
    UploadProgress,
    UploadVerificationRequest,
)


class PublishingPlatform(ABC):
    """Abstract interface every publishing platform adapter implements
    (ARCHITECTURE.md SS24.2). The controller and every contract are written
    against this interface only - they never know they're talking to YouTube,
    TikTok, or anything else specifically. Adding a new platform means
    writing one class that implements this interface and registering it in
    platforms/registry.py - zero changes here, in the controller, or in any
    other platform's code.

    Each method is boundary (real network I/O) and, past the pre-flight
    stage, never raises for a failure that happens once the network call is
    actually made - it returns a structured result instead (PublishResult /
    PublishValidationReport), the same "reportable, not exceptional"
    convention execution_engine's boundary modules established for
    RenderResult.
    """

    platform_name: str

    @abstractmethod
    def validate_credentials(self, credentials: PlatformCredentials) -> PublishValidationReport:
        """Structural-only check (Milestone P3): are the fields this
        platform needs present and non-empty? Never makes a network call and
        never confirms the credentials actually work against the platform -
        that remains authenticate()'s job (still unimplemented). Which field
        names are required is platform-specific knowledge that lives here,
        in the adapter, not in the controller or the registry."""
        ...

    @abstractmethod
    def authenticate(self, credentials: PlatformCredentials) -> AuthenticationResult:
        """Confirm the given credentials actually work against the real
        platform - Milestone P4: one minimal, read-only request, nothing
        more. Reports success/failure as data and never raises itself - a
        missing/invalid/expired credential, a missing scope, a network
        failure, or an API error are all AuthenticationResult(success=False,
        error_type=...), never an exception."""
        ...

    @abstractmethod
    def upload(
        self,
        request: PublishRequest,
        credentials: PlatformCredentials,
        *,
        progress_callback: Optional[Callable[[UploadProgress], None]] = None,
    ) -> PublishResult:
        """Upload request.video_path as a resumable transfer (Milestone
        P7.1's foundation: create a session, upload in chunks, recover from
        interruption, persist session state for later recovery - not yet
        metadata submission beyond what the platform's insert call itself
        requires, not thumbnail upload, not playlist assignment, not
        scheduling). Visibility defaults to private unless
        request.options.visibility_override is explicitly set - see
        PublishOptions. Owns retry/backoff and resumable-session handling
        internally (ARCHITECTURE.md SS24.5). Never raises for a failed or
        interrupted upload - always returns a PublishResult; an interrupted
        upload leaves its UploadSession resumable rather than discarded.

        success=True here means only that the platform accepted every byte -
        it is NOT, by itself, a successful publish. A caller MUST treat this
        as process diagnostics only and separately confirm the result via
        check_status() before considering anything "published" (see
        check_status's own docstring)."""
        ...

    @abstractmethod
    def check_status(self, request: UploadVerificationRequest, credentials: PlatformCredentials) -> PublishValidationReport:
        """Comprehensive postflight verification (Milestone P7.3) of an
        uploaded video, translated into a PublishValidationReport - the
        same pass/fail-checks shape postflight.validate_render already
        establishes for renders. Checks: the video exists/is retrievable,
        processing has reached a terminal state (polling up to
        request.max_poll_attempts, request.poll_interval_seconds apart -
        "still uploading" is not accepted as good enough), privacy status
        matches request.expected_visibility, duration is within
        request.duration_tolerance_seconds of request.expected_duration_seconds
        (skipped, not failed, when that's None), title and description match,
        and the video belongs to the authenticated channel.

        is_valid=True is the ONLY thing that should ever be treated as "the
        upload is confirmed published" - upload()'s success=True means only
        that bytes were accepted, never this. Never raises - any failure
        along the way (auth, network, API, not-found) is reported as failed
        checks, not an exception."""
        ...

from datetime import UTC, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from shared_core.contracts.publishing_metadata import PublishingPlan


class PublishOptions(BaseModel):
    """Execution-technical configuration only - no metadata decisions live
    here (those were all made by Producer Studio's Publishing Metadata stage
    and live on PublishingPlan). Mirrors RenderOptions' role for the
    Execution Engine (ARCHITECTURE.md SS24.3).

    visibility_override is the ONLY way an upload (Milestone P7.1) is ever
    given a visibility other than "private" - PublishingPlan.youtube.visibility
    is deliberately NOT consulted for this. This is a hard safety default,
    not a convenience default: a mistake anywhere upstream (a stale plan, a
    bad default in a future planning stage) must never be able to make an
    upload public on its own. A human sets visibility_override explicitly,
    per upload, to publish as anything other than private."""

    platform: str = "youtube"
    visibility_override: Optional[str] = None
    scheduled_publish_at: Optional[datetime] = None
    dry_run: bool = False
    timeout_seconds: Optional[int] = None
    poll_interval_seconds: int = 10
    max_poll_attempts: int = 30


class AuthenticationResult(BaseModel):
    """Structured outcome of PublishingPlatform.authenticate() (Milestone
    P4) - mirrors RenderResult/PublishResult's "reportable, not exceptional"
    convention: a failed authentication attempt is data, never an exception.
    error_type classifies every failure mode authenticate() must handle:
    "missing_credentials" (structural check failed before any network call),
    "invalid_credentials" (the platform rejected the token, e.g. HTTP 401),
    "expired_token" (the refresh token itself was rejected while refreshing
    - google-auth's RefreshError), "missing_scopes" (the token is valid but
    lacks the required permission, e.g. HTTP 403), "network_error" (the
    request never got a response - DNS/timeout/connection failure),
    "api_error" (any other non-2xx response from the platform),
    "unsupported_platform" (the requested platform isn't registered -
    PublishingEngineController, Milestone P5), or "rate_limited" (a real
    attempt was skipped because a previous one is still within the
    controller's minimum retry interval - AuthenticationCache, Milestone
    P5)."""

    success: bool
    platform: str = ""
    account_label: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    error_type: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlatformCredentials(BaseModel):
    """A structural-only credential bundle (ARCHITECTURE.md SS24, Milestone
    P3). fields is intentionally an opaque string map - which keys are
    required is platform-specific knowledge that belongs entirely inside
    each platform adapter's validate_credentials() (e.g. YouTubePlatform
    expects "client_id"/"client_secret"/"refresh_token"), never in the
    controller or the registry. Values are never validated against the real
    platform here - only checked for presence and non-empty shape. Nothing
    in the Publishing Engine logs or persists these values."""

    platform: str
    fields: Dict[str, str] = Field(default_factory=dict)


class PublishReadinessRequest(BaseModel):
    """Typed input to publishing_engine.preflight.validate_publish_readiness
    (ARCHITECTURE.md SS24, Milestone P2). Deliberately raw paths and a plain
    status string, not an already-loaded Project/PublishingPlan - preflight
    must be able to detect a missing/malformed publishing_metadata.json or an
    unset video path itself, which an already-successfully-parsed object
    could never represent. publishing_engine has no dependency on
    project_manager (Milestone P2's explicit boundary), so project_status is
    a plain string rather than the ProjectState enum - callers pass
    project.status.value (or any equal string)."""

    project_status: str
    video_path: str
    publishing_metadata_path: str
    platform: str = "youtube"
    output_dir: str = ""


class PublishRequest(BaseModel):
    """The typed bundle a PublishingPlatform.upload() call consumes - the
    already-finished PublishingPlan plus the already-rendered video (and an
    optional thumbnail), the render output directory, and the caller's
    options. Mirrors RenderRequest's role for the Execution Engine."""

    publishing_plan: PublishingPlan
    video_path: str
    thumbnail_path: Optional[str] = None
    output_dir: str
    options: PublishOptions = Field(default_factory=PublishOptions)


class UploadSession(BaseModel):
    """Persisted resumable-upload session state (Milestone P7.1,
    ARCHITECTURE.md SS24.5's resumable-upload design, now implemented). The
    primary duplicate-upload guard: before starting a new session,
    YouTubePlatform.upload() looks for an existing one keyed by
    content_fingerprint (a cheap size+mtime fingerprint of the video file,
    not a full-file hash - "avoid duplicate uploads where practical", not an
    exhaustive integrity guarantee). status="completed" means the caller
    gets external_video_id back immediately with no new upload attempt at
    all; status="in_progress" means the caller resumes from bytes_uploaded
    (re-confirmed against the platform via a status-check request, since a
    process crash may have lost the last acknowledgment)."""

    platform: str
    session_uri: str
    video_path: str
    content_fingerprint: str
    total_bytes: int
    bytes_uploaded: int = 0
    external_video_id: Optional[str] = None
    status: str = "in_progress"  # "in_progress" | "completed" | "failed"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UploadProgress(BaseModel):
    """One reportable progress update during a resumable upload (Milestone
    P7.1) - what YouTubePlatform.upload()'s optional progress_callback
    receives after each successfully-acknowledged chunk, so a caller (CLI, a
    future scheduler) can show progress without polling the platform
    directly."""

    bytes_uploaded: int
    total_bytes: int
    percent_complete: float
    status: str  # "in_progress" | "completed" | "failed"


class UploadVerificationRequest(BaseModel):
    """Typed input to PublishingPlatform.check_status() (Milestone P7.3,
    Full Postflight Verification). A video id alone (P7.2's narrower
    check_status) isn't enough to verify title/description/visibility/
    duration match what was planned - those expected values have to come
    from the caller, since publishing_engine never loads a PublishingPlan or
    EditingPlan itself for this comparison (it only ever receives raw values
    it's handed, the same discipline PublishReadinessRequest established in
    Milestone P2). expected_duration_seconds is the one field with no
    natural source inside publishing_engine at all - it comes from the
    Producer Package's EditingPlan, which publishing_engine never imports -
    so it is Optional: a caller that doesn't have it yet simply gets the
    duration check reported as skipped rather than failed.

    poll_interval_seconds/max_poll_attempts reuse the exact meaning
    PublishOptions already reserved for them since the contract's earliest
    revision - check_status() polls for a terminal processing state
    (processed/failed/rejected/deleted) rather than accepting "still
    uploading" as good enough for a "comprehensive" verification verdict."""

    external_video_id: str
    expected_title: str
    expected_description: str
    expected_visibility: str
    expected_duration_seconds: Optional[float] = None
    duration_tolerance_seconds: float = 2.0
    poll_interval_seconds: int = 10
    max_poll_attempts: int = 30


class PublishResult(BaseModel):
    """The Publishing Engine's structured PROCESS outcome - what a platform
    adapter's upload() always returns instead of raising, mirroring
    RenderResult. success=True here means only that the platform accepted the
    upload - it is process diagnostics, NOT verified publication (processing
    status, public visibility). project.status is never advanced on a
    PublishResult alone; see PublishValidationReport. bytes_uploaded/
    total_bytes/session are populated once an upload attempt has actually
    started (Milestone P7.1) - session is the persisted UploadSession a
    later, separate call can use to resume or to confirm "already done"."""

    success: bool
    dry_run: bool = False
    platform: str = ""
    external_video_id: Optional[str] = None
    external_url: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    retry_count: int = 0
    bytes_uploaded: int = 0
    total_bytes: int = 0
    session: Optional[UploadSession] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # "missing_credentials" | "expired_token" | "invalid_credentials" |
    # "network_error" | "session_create_failed" | "api_error" | "interrupted" (a chunk upload didn't finish,
    # but the session was left "in_progress" and is resumable by a later call) | None


class PublishValidationCheck(BaseModel):
    """One concrete, human-readable postflight comparison - mirrors
    RenderValidationCheck's role for the Execution Engine: each check names
    what was expected and what a platform's check_status() actually
    reported."""

    name: str  # "upload_accepted" | "processing_status" | "video_public_state" | "metadata_applied"
    passed: bool
    expected: str
    actual: str


class PublishValidationReport(BaseModel):
    """Structured validation verdict for the Publishing Engine. Serves two
    moments that share the same shape and the same file name
    (publish_validation.json), distinguished by which fields are populated:

    - PRE-flight readiness (Milestone P2, publishing_engine.preflight):
      is_valid=True means the project is *ready to attempt* a publish - state
      correct, video present and readable, metadata present with required
      fields, platform supported, request well-formed. external_video_id/url
      are None here; nothing has been uploaded yet.
    - POST-flight verification (a later milestone, after an actual upload):
      is_valid=True means the platform confirmed the upload actually
      finished processing correctly. external_video_id/url are populated.

    Mirrors RenderValidationReport's role: is_valid=True is the ONLY thing
    that permits PUBLISHED to be set (once a later milestone adds that
    transition) - a platform accepting an upload is necessary but not
    sufficient on its own."""

    is_valid: bool
    checks: List[PublishValidationCheck] = Field(default_factory=list)
    platform: str = ""
    external_video_id: Optional[str] = None
    external_url: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReadyToPublishResult(BaseModel):
    """Everything PublishingEngineController.run() resolves and validates
    before an upload could even be attempted. Introduced as PublishContext
    in Milestone P3 (readiness + structural credential checks only); renamed
    and extended with `authentication` in Milestone P5, once the controller
    actually wires in real authentication - "ready to publish" now means the
    credentials were confirmed to actually work, not just that their fields
    were present.

    Purely an in-memory assembly - nothing here is written to disk (no
    publish report exists yet), and nothing here performs an upload. request
    is populated only when readiness, credentials, AND authentication are
    all valid (ready_to_publish=True) and a PublishingPlan was supplied -
    there is nothing useful to hand a future upload step otherwise, the same
    "don't persist what's incomplete" principle save_render_result already
    applies to project state."""

    platform: str
    dry_run: bool
    readiness: PublishValidationReport
    credentials: PublishValidationReport
    authentication: AuthenticationResult
    ready_to_publish: bool
    request: Optional[PublishRequest] = None

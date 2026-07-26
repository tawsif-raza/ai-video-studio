"""
A successful HTTP upload must not automatically imply a successful publish.
platform.upload()'s success=True means only that the platform accepted every
byte over the wire - it says nothing about whether the resulting video
object actually exists, finished processing, has the right visibility, or
matches the planned metadata. perform_upload enforces full postflight
verification (Milestone P7.3) as a required, separate step, never skipped
and never conflated with the upload's own success flag.

This lives outside PublishingEngineController on purpose - the controller's
documented boundary (Milestone P5) is readiness/authentication only, and it
never uploads. Kept here as its own small orchestration function instead:
one place that sequences "upload, then verify" without pretending the two
are one operation, and without adding upload/verification responsibility to
either the controller or a platform-agnostic caller.

Does not touch project state and does not persist anything - persistence is
Project Manager's job, exactly as ARCHITECTURE.md SS4/SS24 established for
every other Publishing Engine report.
"""

from typing import Callable, Optional, Tuple

from publishing_engine.platforms.base import PublishingPlatform
from shared_core.contracts.publish import (
    PlatformCredentials,
    PublishRequest,
    PublishResult,
    PublishValidationReport,
    UploadProgress,
    UploadVerificationRequest,
)


def perform_upload(
    *,
    platform: PublishingPlatform,
    request: PublishRequest,
    credentials: PlatformCredentials,
    expected_duration_seconds: Optional[float] = None,
    progress_callback: Optional[Callable[[UploadProgress], None]] = None,
) -> Tuple[PublishResult, Optional[PublishValidationReport]]:
    """Uploads, then - only if the upload itself succeeded and produced a
    video id - runs full postflight verification. verification is None when
    there was nothing to verify (the upload didn't succeed, or a dry-run
    produced no real video), never a fabricated pass. The caller persists
    both and decides what (if anything) that means for project state - this
    function decides neither.

    expected_title/description/visibility come from request.publishing_plan/
    request.options - the same values upload() itself used to build the
    video. expected_duration_seconds has no natural source inside
    publishing_engine (it lives on the Producer Package's EditingPlan,
    which publishing_engine never imports - Milestone P2's boundary), so
    it's an explicit parameter a future caller supplies from wherever it
    has that value; omitting it simply skips the duration check rather than
    failing verification."""
    upload_result = platform.upload(request, credentials, progress_callback=progress_callback)

    if not upload_result.success or not upload_result.external_video_id:
        return upload_result, None

    plan = request.publishing_plan
    verification_request = UploadVerificationRequest(
        external_video_id=upload_result.external_video_id,
        expected_title=plan.youtube.title,
        expected_description=plan.youtube.description,
        expected_visibility=request.options.visibility_override or "private",
        expected_duration_seconds=expected_duration_seconds,
        poll_interval_seconds=request.options.poll_interval_seconds,
        max_poll_attempts=request.options.max_poll_attempts,
    )
    verification = platform.check_status(verification_request, credentials)
    return upload_result, verification

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Optional

import requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials as GoogleCredentials

from publishing_engine.platforms.base import PublishingPlatform
from publishing_engine.platforms.youtube_resumable import YouTubeResumableUpload
from publishing_engine.upload_session_store import FileUploadSessionStore, fingerprint_video_file
from shared_core.contracts.publish import (
    AuthenticationResult,
    PlatformCredentials,
    PublishRequest,
    PublishResult,
    PublishValidationCheck,
    PublishValidationReport,
    UploadProgress,
    UploadSession,
    UploadVerificationRequest,
)


# YouTube Data API v3 uploads authenticate via OAuth 2.0 (installed-app
# flow), not a bare API key - client_id/client_secret identify the app,
# refresh_token is the long-lived credential that stands in for a signed-in
# user. All three are required to refresh an access token at all.
REQUIRED_CREDENTIAL_FIELDS = ("client_id", "client_secret", "refresh_token")

# status.uploadStatus values that mean processing has finished one way or
# another - polling stops as soon as one of these is seen, rather than only
# ever accepting "uploaded" (still processing) as if it were a pass.
TERMINAL_UPLOAD_STATUSES = ("processed", "failed", "rejected", "deleted")

_ISO8601_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")


def _parse_iso8601_duration(value: Optional[str]) -> Optional[float]:
    """"PT1M30S" -> 90.0. YouTube's contentDetails.duration is always this
    ISO 8601 form; returns None for anything that doesn't match rather than
    raising, since a malformed/missing duration is reportable data here, not
    an exception."""
    if not value:
        return None
    match = _ISO8601_DURATION_RE.fullmatch(value)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return (int(hours or 0) * 3600) + (int(minutes or 0) * 60) + float(seconds or 0)


class YouTubePlatform(PublishingPlatform):
    """First, and only v1, PublishingPlatform implementation - targets the
    YouTube Data API v3 (ARCHITECTURE.md SS24.2).

    - Milestone P3: validate_credentials is real but structural-only - zero
      network calls, only checks that expected fields are present.
    - Milestone P4: authenticate is real - it refreshes the given credentials
      into a live access token and makes exactly one minimal, read-only
      YouTube Data API call to confirm the token actually works.
    - Milestone P7.1: upload is real - resumable-transfer FOUNDATION only.
      Creates a session (or resumes an existing persisted one), uploads in
      chunks, recovers from interruption at the protocol level (see
      youtube_resumable.py), and persists session state after every chunk
      so a later, separate call can recover. Visibility defaults to
      private unless request.options.visibility_override is explicitly
      set - PublishingPlan.youtube.visibility is deliberately never
      consulted for this (see PublishOptions). Does NOT yet: update
      metadata beyond what the insert call itself requires, upload a
      thumbnail, assign a playlist, schedule anything, or set project state
      to PUBLISHED - all later milestones.
    - Milestone P7.3: check_status is comprehensive - video exists,
      processing has reached a terminal state (polling, not just checking
      once), privacy status, duration, title, description, and channel
      ownership. A successful upload() is still explicitly NOT treated as a
      successful publish anywhere in this codebase - is_valid on
      check_status()'s report is the only thing that means "verified".

    All HTTP-capable dependencies are constructor-injectable so unit tests
    never touch the network - the same dependency-injection convention
    ExecutionEngineController/PublishingEngineController already use.
    """

    platform_name = "youtube"

    TOKEN_URI = "https://oauth2.googleapis.com/token"
    CHANNELS_ENDPOINT = "https://www.googleapis.com/youtube/v3/channels"
    VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"
    READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
    UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        credentials_factory=GoogleCredentials,
        auth_request_factory=GoogleAuthRequest,
        http_get=requests.get,
        resumable_upload_factory: Callable[..., YouTubeResumableUpload] = YouTubeResumableUpload,
        session_store_factory: Callable[[str], FileUploadSessionStore] = FileUploadSessionStore,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._timeout_seconds = timeout_seconds
        self._credentials_factory = credentials_factory
        self._auth_request_factory = auth_request_factory
        self._http_get = http_get
        self._resumable_upload_factory = resumable_upload_factory
        self._session_store_factory = session_store_factory
        self._sleep = sleep

    def validate_credentials(self, credentials: PlatformCredentials) -> PublishValidationReport:
        checks = [
            PublishValidationCheck(
                name=f"credential_{field}",
                passed=bool(credentials.fields.get(field, "").strip()),
                expected="non-empty value",
                actual="present" if credentials.fields.get(field, "").strip() else "missing",
            )
            for field in REQUIRED_CREDENTIAL_FIELDS
        ]
        return PublishValidationReport(
            is_valid=all(check.passed for check in checks),
            checks=checks,
            platform=self.platform_name,
        )

    def _refresh_google_credentials(self, credentials: PlatformCredentials, *, scopes: list):
        """Returns (google_credentials, error, error_type) - google_credentials
        is None iff error is set. Shared by authenticate() and upload() so
        the refresh logic (and its failure classification) exists once."""
        validation = self.validate_credentials(credentials)
        if not validation.is_valid:
            missing = [c.name.removeprefix("credential_") for c in validation.checks if not c.passed]
            return None, f"missing credential fields: {', '.join(missing)}", "missing_credentials"

        google_credentials = self._credentials_factory(
            token=None,
            refresh_token=credentials.fields["refresh_token"],
            token_uri=self.TOKEN_URI,
            client_id=credentials.fields["client_id"],
            client_secret=credentials.fields["client_secret"],
            scopes=scopes,
        )
        try:
            google_credentials.refresh(self._auth_request_factory())
        except RefreshError as e:
            return None, str(e), "expired_token"
        except requests.exceptions.RequestException as e:
            return None, str(e), "network_error"
        return google_credentials, None, None

    def authenticate(self, credentials: PlatformCredentials) -> AuthenticationResult:
        google_credentials, error, error_type = self._refresh_google_credentials(
            credentials, scopes=[self.READONLY_SCOPE]
        )
        if error is not None:
            return self._auth_failure(error, error_type)

        try:
            response = self._http_get(
                self.CHANNELS_ENDPOINT,
                params={"part": "id,snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {google_credentials.token}"},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            return self._auth_failure(str(e), "network_error")

        if response.status_code == 401:
            return self._auth_failure("YouTube API rejected the access token", "invalid_credentials")
        if response.status_code == 403:
            return self._auth_failure(f"YouTube API denied the request: {response.text}", "missing_scopes")
        if response.status_code >= 400:
            return self._auth_failure(f"YouTube API error {response.status_code}: {response.text}", "api_error")

        items = response.json().get("items", [])
        account_label = items[0]["snippet"]["title"] if items and "snippet" in items[0] else None

        return AuthenticationResult(
            success=True,
            platform=self.platform_name,
            account_label=account_label,
            scopes=list(google_credentials.scopes or []),
        )

    def _auth_failure(self, error: str, error_type: str) -> AuthenticationResult:
        return AuthenticationResult(success=False, platform=self.platform_name, error=error, error_type=error_type)

    def upload(
        self,
        request: PublishRequest,
        credentials: PlatformCredentials,
        *,
        progress_callback: Optional[Callable[[UploadProgress], None]] = None,
    ) -> PublishResult:
        started_at = datetime.now(UTC)

        # A deliberate, redundant safety check: everywhere else in this
        # codebase, dry-run branching lives only in the caller/controller,
        # never inside the boundary method itself (ARCHITECTURE.md SS7/SS24
        # - "the branch lives in the controller, keeping the executor pure").
        # upload() breaks that convention on purpose: it is the one
        # operation in the whole system with a real, hard-to-reverse
        # external side effect (a real video created on a real channel), so
        # this method refuses to make any network call at all when
        # dry_run=True, regardless of what any caller does or doesn't check.
        if request.options.dry_run:
            return PublishResult(
                success=True, dry_run=True, platform=self.platform_name,
                started_at=started_at, finished_at=started_at,
            )

        google_credentials, error, error_type = self._refresh_google_credentials(
            credentials, scopes=[self.UPLOAD_SCOPE]
        )
        if error is not None:
            return self._upload_failure(started_at, error, error_type)

        try:
            total_bytes = Path(request.video_path).stat().st_size
        except OSError as e:
            return self._upload_failure(started_at, str(e), "upload_failed")

        fingerprint = fingerprint_video_file(request.video_path)
        store = self._session_store_factory(request.output_dir)
        resumable = self._resumable_upload_factory(timeout_seconds=self._timeout_seconds)

        session, resume_from, early_result = self._resolve_session(
            store=store, resumable=resumable, fingerprint=fingerprint, request=request,
            total_bytes=total_bytes, access_token=google_credentials.token,
            started_at=started_at,
        )
        if early_result is not None:
            return early_result

        def _persist_progress(progress: UploadProgress) -> None:
            session.bytes_uploaded = progress.bytes_uploaded
            session.status = progress.status
            session.updated_at = datetime.now(UTC)
            store.save(session)
            if progress_callback:
                progress_callback(progress)

        success, bytes_uploaded, video_id, upload_error = resumable.upload_file(
            session_uri=session.session_uri,
            video_path=request.video_path,
            total_bytes=total_bytes,
            access_token=google_credentials.token,
            resume_from=resume_from,
            progress_callback=_persist_progress,
        )

        finished_at = datetime.now(UTC)
        session.bytes_uploaded = bytes_uploaded
        session.updated_at = finished_at
        if success and video_id:
            session.status = "completed"
            session.external_video_id = video_id
        elif not success:
            session.status = "failed" if upload_error == "session_expired" else "in_progress"
        store.save(session)

        if not success:
            return PublishResult(
                success=False, platform=self.platform_name, bytes_uploaded=bytes_uploaded, total_bytes=total_bytes,
                session=session, started_at=started_at, finished_at=finished_at,
                error=upload_error,
                error_type="interrupted" if session.status == "in_progress" else "api_error",
            )

        return PublishResult(
            success=True, platform=self.platform_name, external_video_id=video_id,
            bytes_uploaded=bytes_uploaded, total_bytes=total_bytes, session=session,
            started_at=started_at, finished_at=finished_at,
        )

    def _resolve_session(self, *, store, resumable, fingerprint, request, total_bytes, access_token, started_at):
        """Returns (session, resume_from, early_result). early_result is
        non-None when there's nothing left to upload (already completed) or
        session creation itself failed - the caller returns it directly."""
        existing = store.load(fingerprint)

        if existing is not None and existing.status == "completed" and existing.external_video_id:
            return existing, existing.total_bytes, PublishResult(
                success=True, platform=self.platform_name, external_video_id=existing.external_video_id,
                bytes_uploaded=existing.total_bytes, total_bytes=existing.total_bytes, session=existing,
                started_at=started_at, finished_at=datetime.now(UTC),
            )

        if existing is not None and existing.status == "in_progress":
            resume_from, video_id_from_query, query_error = resumable.query_uploaded_bytes(
                session_uri=existing.session_uri, total_bytes=total_bytes
            )
            if query_error is None and resume_from is not None:
                if video_id_from_query:
                    existing.status, existing.bytes_uploaded, existing.external_video_id = (
                        "completed", total_bytes, video_id_from_query,
                    )
                    existing.updated_at = datetime.now(UTC)
                    store.save(existing)
                    return existing, total_bytes, PublishResult(
                        success=True, platform=self.platform_name, external_video_id=video_id_from_query,
                        bytes_uploaded=total_bytes, total_bytes=total_bytes, session=existing,
                        started_at=started_at, finished_at=datetime.now(UTC),
                    )
                return existing, resume_from, None
            # session no longer valid on the platform side - fall through and start a fresh one

        visibility = request.options.visibility_override or "private"
        plan = request.publishing_plan
        session_uri, error = resumable.create_session(
            access_token=access_token,
            total_bytes=total_bytes,
            snippet={
                "title": plan.youtube.title,
                "description": plan.youtube.description,
                "tags": plan.youtube.tags,
                "categoryId": plan.youtube.category,
            },
            status={"privacyStatus": visibility},
        )
        if error is not None:
            return None, 0, self._upload_failure(started_at, error, "session_create_failed")

        new_session = UploadSession(
            platform=self.platform_name, session_uri=session_uri, video_path=request.video_path,
            content_fingerprint=fingerprint, total_bytes=total_bytes, bytes_uploaded=0, status="in_progress",
        )
        store.save(new_session)
        return new_session, 0, None

    def _upload_failure(self, started_at, error: str, error_type: str) -> PublishResult:
        return PublishResult(
            success=False, platform=self.platform_name, error=error, error_type=error_type,
            started_at=started_at, finished_at=datetime.now(UTC),
        )

    def check_status(
        self, request: UploadVerificationRequest, credentials: PlatformCredentials
    ) -> PublishValidationReport:
        google_credentials, error, error_type = self._refresh_google_credentials(
            credentials, scopes=[self.READONLY_SCOPE]
        )
        if error is not None:
            return self._all_checks_failed(request, reason=f"{error_type}: {error}")

        video, upload_status, fetch_error = self._poll_for_terminal_status(
            video_id=request.external_video_id,
            access_token=google_credentials.token,
            max_attempts=max(1, request.max_poll_attempts),
            poll_interval_seconds=request.poll_interval_seconds,
        )
        if fetch_error is not None:
            return self._all_checks_failed(request, reason=fetch_error)
        if video is None:
            return self._all_checks_failed(request, reason="video not found via the YouTube Data API")

        channel_id, channel_error = self._fetch_authenticated_channel_id(access_token=google_credentials.token)

        checks = [
            PublishValidationCheck(
                name="video_exists", passed=True,
                expected=f"video id {request.external_video_id} retrievable via the YouTube Data API",
                actual="present",
            ),
            self._check_processing_status(upload_status),
            self._check_privacy(video, request.expected_visibility),
            self._check_duration(video, request.expected_duration_seconds, request.duration_tolerance_seconds),
            self._check_title(video, request.expected_title),
            self._check_description(video, request.expected_description),
            self._check_channel_ownership(video, channel_id, channel_error),
        ]

        is_valid = all(check.passed for check in checks)
        return PublishValidationReport(
            is_valid=is_valid,
            platform=self.platform_name,
            checks=checks,
            external_video_id=request.external_video_id if is_valid else None,
        )

    def _poll_for_terminal_status(self, *, video_id, access_token, max_attempts, poll_interval_seconds):
        """Fetches the video repeatedly until status.uploadStatus reaches a
        terminal state or max_attempts is exhausted - "uploaded" (still
        processing) is not accepted as if it were done. Returns
        (video_or_None, last_upload_status_or_None, fetch_error_or_None)."""
        video = None
        upload_status = None
        for attempt in range(max_attempts):
            video, fetch_error = self._fetch_video(video_id=video_id, access_token=access_token)
            if fetch_error is not None:
                return None, None, fetch_error
            if video is None:
                return None, None, None
            upload_status = video.get("status", {}).get("uploadStatus")
            if upload_status in TERMINAL_UPLOAD_STATUSES:
                break
            if attempt < max_attempts - 1:
                self._sleep(poll_interval_seconds)
        return video, upload_status, None

    def _fetch_video(self, *, video_id: str, access_token: str):
        """Returns (video_or_None, error_or_None). video=None with
        error=None means "not found" - not a request failure."""
        try:
            response = self._http_get(
                self.VIDEOS_ENDPOINT,
                params={"part": "snippet,status,contentDetails", "id": video_id},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            return None, f"network_error: {e}"
        if response.status_code >= 400:
            return None, f"api_error {response.status_code}: {response.text}"
        items = response.json().get("items", [])
        if not items or items[0].get("id") != video_id:
            return None, None
        return items[0], None

    def _fetch_authenticated_channel_id(self, *, access_token: str):
        """Returns (channel_id_or_None, error_or_None) - reused from the
        same channels.list?mine=true call authenticate() already makes,
        scoped down to just the id here since that's all ownership
        comparison needs."""
        try:
            response = self._http_get(
                self.CHANNELS_ENDPOINT,
                params={"part": "id", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            return None, f"network_error: {e}"
        if response.status_code >= 400:
            return None, f"api_error {response.status_code}: {response.text}"
        items = response.json().get("items", [])
        if not items:
            return None, "no channel found for the authenticated user"
        return items[0].get("id"), None

    def _check_processing_status(self, upload_status: Optional[str]) -> PublishValidationCheck:
        return PublishValidationCheck(
            name="processing_status",
            passed=upload_status == "processed",
            expected="processed",
            actual=upload_status or "unknown",
        )

    def _check_privacy(self, video: dict, expected_visibility: str) -> PublishValidationCheck:
        actual = video.get("status", {}).get("privacyStatus")
        return PublishValidationCheck(
            name="privacy_status", passed=actual == expected_visibility,
            expected=expected_visibility, actual=actual or "unknown",
        )

    def _check_duration(self, video: dict, expected_seconds: Optional[float], tolerance: float) -> PublishValidationCheck:
        actual_seconds = _parse_iso8601_duration(video.get("contentDetails", {}).get("duration"))
        if expected_seconds is None:
            return PublishValidationCheck(
                name="duration", passed=True, expected="not specified - skipped",
                actual=f"{actual_seconds}s" if actual_seconds is not None else "unknown",
            )
        if actual_seconds is None:
            return PublishValidationCheck(
                name="duration", passed=False,
                expected=f"{expected_seconds}s (+/- {tolerance}s)", actual="unavailable",
            )
        passed = abs(actual_seconds - expected_seconds) <= tolerance
        return PublishValidationCheck(
            name="duration", passed=passed,
            expected=f"{expected_seconds}s (+/- {tolerance}s)", actual=f"{actual_seconds}s",
        )

    def _check_title(self, video: dict, expected_title: str) -> PublishValidationCheck:
        actual = (video.get("snippet", {}).get("title") or "").strip()
        return PublishValidationCheck(
            name="title_matches", passed=actual == expected_title.strip(),
            expected=expected_title, actual=actual,
        )

    def _check_description(self, video: dict, expected_description: str) -> PublishValidationCheck:
        actual = (video.get("snippet", {}).get("description") or "").strip()
        return PublishValidationCheck(
            name="description_matches", passed=actual == expected_description.strip(),
            expected=expected_description, actual=actual,
        )

    def _check_channel_ownership(self, video: dict, channel_id: Optional[str], channel_error: Optional[str]) -> PublishValidationCheck:
        actual = video.get("snippet", {}).get("channelId")
        if channel_error is not None:
            return PublishValidationCheck(
                name="channel_ownership", passed=False,
                expected="uploaded video's channelId matches the authenticated channel", actual=channel_error,
            )
        return PublishValidationCheck(
            name="channel_ownership", passed=bool(actual) and actual == channel_id,
            expected=channel_id or "unknown", actual=actual or "unknown",
        )

    def _all_checks_failed(self, request: UploadVerificationRequest, *, reason: str) -> PublishValidationReport:
        """Used when nothing past a certain point could even be checked
        (auth failure, fetch failure, or the video genuinely not found) -
        every check still appears, all failed with the same reason, so the
        report's shape is always the same seven checks regardless of how
        early verification stopped."""
        names_and_expectations = (
            ("video_exists", f"video id {request.external_video_id} retrievable via the YouTube Data API"),
            ("processing_status", "processed"),
            ("privacy_status", request.expected_visibility),
            ("duration", f"{request.expected_duration_seconds}s (+/- {request.duration_tolerance_seconds}s)" if request.expected_duration_seconds is not None else "not specified"),
            ("title_matches", request.expected_title),
            ("description_matches", request.expected_description),
            ("channel_ownership", "uploaded video's channelId matches the authenticated channel"),
        )
        checks = [
            PublishValidationCheck(name=name, passed=False, expected=expected, actual=reason)
            for name, expected in names_and_expectations
        ]
        return PublishValidationReport(is_valid=False, platform=self.platform_name, checks=checks, external_video_id=None)

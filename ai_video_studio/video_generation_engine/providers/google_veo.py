"""
Real Google Veo video generation provider (ARCHITECTURE.md SS25.5, Milestone
V3: Real Google Veo Provider). Talks to the Gemini Developer API's async
video generation endpoint through the official google-genai SDK
(client.models.generate_videos) - the same SDK llm/gemini_image_client.py
already uses for image generation, and already a pinned dependency
(requirements.txt: google-genai>=1.0).

Registered under "google_veo" (provider_registry.py) - the name
VideoGenerationOptions.provider already defaults to. Milestone V2 registered
no adapter for it on purpose (a bare default failed closed); this class is
that adapter.

Credentials: resolved lazily, inside __init__, from config.py/environment
only (settings.GOOGLE_VEO_API_KEY, itself falling back to the same
GEMINI_API_KEY llm/gemini_image_client.py already reads) - never a field on
any contract, never logged (module docstring in
shared_core/contracts/video_generation.py, SS25.9). authenticate() reports a
missing key as ProviderInfo(available=False, ...) rather than raising - the
controller decides whether that's fatal (VideoGenerationEnvironmentError).
Nothing in this module ever formats an exception's raw response body or
request headers into a log/error string - see _describe_exception.

Async lifecycle - the entire submit -> poll -> download sequence lives here,
inside generate(), not the controller (SS25.8): client.models.generate_videos
returns a long-running Operation immediately; this polls
client.operations.get(operation) on a fixed interval
(options.poll_interval_seconds) with a plain time.sleep between checks
(never a busy loop), bounded by BOTH options.max_poll_attempts and, if set,
options.timeout_seconds as an independent wall-clock ceiling - whichever is
hit first ends the job as a "timeout" result, never an exception.

Request mapping (verified against the installed google-genai==2.11.0 SDK's
own GenerateVideosConfig fields and https://ai.google.dev/gemini-api/docs/veo
- see _map_config): only prompt, image (seed_image_path), aspect_ratio,
resolution, duration_seconds, and number_of_videos=1 are sent - no
unsupported/invented Veo parameter (negative_prompt, generate_audio,
enhance_prompt, seed, etc.) is used, since none of those have a field on
VideoGenerationOptions/VideoGenerationRequest. Veo only accepts
aspect_ratio in {"16:9", "9:16"}, resolution in {"720p", "1080p"}, and
duration_seconds in {4, 6, 8} - a shot whose planned duration isn't exactly
one of those is rounded to the nearest supported value (documented
limitation - see _map_config's docstring), not rejected outright.

Download: client.files.download() (the SDK's own helper) always buffers the
entire clip into a Python bytes object before returning (verified by reading
google/genai/_api_client.py:download_file - it does response.read() then
returns). For a single Veo clip (single-digit to double-digit MB) that
wouldn't OOM, but the milestone requires avoiding unnecessary full-file
buffering, so this bypasses that helper: _default_downloader streams the
clip's own public download URI (GeneratedVideo.video.uri, an authenticated
HTTPS URL) directly via httpx.stream(), writing fixed-size chunks straight
to a temporary file on disk and never holding more than one
_DOWNLOAD_CHUNK_BYTES chunk in memory, then atomically renaming to the final
scene_<id>_shot_<id>.mp4 path. httpx is already a pinned dependency
(requirements.txt: httpx>=0.27) and is the same HTTP library google-genai
itself uses internally.
"""

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Optional

import httpx

from config import settings
from shared_core.contracts.video_generation import (
    ProviderInfo,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationStatus,
)
from utils.logger import get_logger
from video_generation_engine.prompt_builder import build_video_prompt
from video_generation_engine.providers.base import VideoGenerationProvider

logger = get_logger("video_generation_engine.providers.google_veo")

SUPPORTED_ASPECT_RATIOS = ("16:9", "9:16")
SUPPORTED_RESOLUTIONS = ("720p", "1080p")
SUPPORTED_DURATIONS_SECONDS = (4, 6, 8)
DEFAULT_RESOLUTION = "720p"

# Common WIDTHxHEIGHT strings (the local StubProvider's own resolution
# convention) mapped onto the nearest Veo resolution preset, so a caller
# reusing the same options across providers doesn't have to know Veo wants
# "720p"/"1080p" specifically. Anything else is passed through as-is and
# validated against SUPPORTED_RESOLUTIONS.
_RESOLUTION_ALIASES = {
    "1280x720": "720p", "720x1280": "720p",
    "1920x1080": "1080p", "1080x1920": "1080p",
}

_DOWNLOAD_CHUNK_BYTES = 256 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 300


def _map_resolution(resolution: Optional[str]) -> str:
    if resolution is None:
        return DEFAULT_RESOLUTION
    if resolution in SUPPORTED_RESOLUTIONS:
        return resolution
    aliased = _RESOLUTION_ALIASES.get(resolution)
    if aliased:
        return aliased
    raise ValueError(
        f"Google Veo does not support resolution '{resolution}' - supported: {SUPPORTED_RESOLUTIONS}"
    )


def _map_duration(requested_seconds: float) -> int:
    """Veo only accepts a fixed set of clip durations (SUPPORTED_DURATIONS_SECONDS).
    Rounds to the nearest supported value rather than rejecting the shot
    outright - postflight.validate_generated_clip's DURATION_TOLERANCE_SECONDS
    (1.0s) already absorbs a difference this small for any shot planned at 4-8s;
    a shot planned well outside that range will still fail postflight
    validation on the resulting mismatch, which is the correct, honest
    outcome rather than silently inventing an unsupported duration."""
    return min(SUPPORTED_DURATIONS_SECONDS, key=lambda d: abs(d - requested_seconds))


def _map_config(request: VideoGenerationRequest):
    """Returns (aspect_ratio, resolution, duration_seconds) or raises ValueError."""
    aspect_ratio = request.options.aspect_ratio
    if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
        raise ValueError(
            f"Google Veo does not support aspect_ratio '{aspect_ratio}' - supported: {SUPPORTED_ASPECT_RATIOS}"
        )
    resolution = _map_resolution(request.options.resolution)
    duration = _map_duration(request.shot_prompt.duration_seconds)
    return aspect_ratio, resolution, duration


def _classify_exception(exc: Exception) -> str:
    """Maps an SDK exception to one of VideoGenerationResult's error_type
    values, using only the HTTP status code (google.genai.errors.APIError.code)
    - never the raw response body, which could echo request details."""
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return "auth_failed"
    if code == 429:
        return "quota_exceeded"
    return "generation_failed"


def _describe_exception(exc: Exception) -> str:
    """Renders an exception to a short, safe message. google-genai's
    APIError.__str__ is '{code} {status}. {details}' - a structured API
    error body, not a credential/header dump - but this is still truncated
    and never passed through anything that could echo an Authorization
    header or API key back out (SS25.9 / milestone requirement 11)."""
    return str(exc)[:2000]


class GoogleVeoProvider(VideoGenerationProvider):
    provider_name = "google_veo"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client=None,
        downloader: Optional[Callable[[str, Path], int]] = None,
    ):
        self._api_key = api_key if api_key is not None else settings.GOOGLE_VEO_API_KEY
        self._model = model or settings.GOOGLE_VEO_MODEL
        self._client_override = client
        self._client = None
        self._downloader = downloader or self._default_downloader

    def _get_client(self):
        if self._client_override is not None:
            return self._client_override
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def authenticate(self) -> ProviderInfo:
        if not self._api_key:
            return ProviderInfo(
                provider=self.provider_name,
                available=False,
                account_label=None,
                detail=(
                    "No Google Veo credentials configured - set GOOGLE_VEO_API_KEY "
                    "(or GEMINI_API_KEY) in the environment/.env"
                ),
            )
        return ProviderInfo(
            provider=self.provider_name,
            available=True,
            account_label=f"google-veo:{self._model}",
            detail=None,
        )

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        started_at = datetime.now(UTC)

        if not self._api_key:
            return self._failure(
                request, started_at, None,
                "No Google Veo credentials configured - set GOOGLE_VEO_API_KEY (or GEMINI_API_KEY)",
                "auth_failed",
            )

        try:
            aspect_ratio, resolution, duration_seconds = _map_config(request)
        except ValueError as exc:
            return self._failure(request, started_at, None, str(exc), "generation_failed")

        seed_path = request.options.seed_image_path
        if seed_path and not Path(seed_path).is_file():
            return self._failure(
                request, started_at, None, f"seed image not found: {seed_path}", "generation_failed",
            )

        try:
            from google.genai import types
        except ImportError as exc:
            return self._failure(
                request, started_at, None, f"google-genai SDK not installed: {exc}", "generation_failed",
            )

        prompt = build_video_prompt(request.shot_prompt, request.options)
        image = types.Image.from_file(location=seed_path) if seed_path else None
        client = self._get_client()

        try:
            operation = client.models.generate_videos(
                model=self._model,
                prompt=prompt,
                image=image,
                config=types.GenerateVideosConfig(
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    duration_seconds=duration_seconds,
                    number_of_videos=1,
                ),
            )
        except Exception as exc:
            return self._failure(
                request, started_at, None, _describe_exception(exc), _classify_exception(exc),
            )

        external_job_id = operation.name

        operation, timeout_error = self._poll_until_done(client, operation, request.options)
        if timeout_error is not None:
            return self._failure(request, started_at, external_job_id, timeout_error, "timeout")

        if operation.error:
            return self._failure(
                request, started_at, external_job_id, _describe_exception_dict(operation.error), "generation_failed",
            )

        response = operation.result or operation.response
        if not response or not response.generated_videos:
            filtered_reasons = getattr(response, "rai_media_filtered_reasons", None) if response else None
            if filtered_reasons:
                return self._failure(
                    request, started_at, external_job_id, "; ".join(filtered_reasons), "content_filtered",
                )
            return self._failure(
                request, started_at, external_job_id, "generation completed with no video returned", "generation_failed",
            )

        generated_video = response.generated_videos[0]
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"scene_{request.scene_id}_shot_{request.shot_id}.mp4"

        try:
            bytes_written = self._save_generated_video(generated_video.video, output_path)
        except Exception as exc:
            return self._failure(
                request, started_at, external_job_id, _describe_exception(exc), "generation_failed",
            )

        logger.info(
            f"[google_veo provider] generated clip for scene {request.scene_id} shot {request.shot_id}: "
            f"{output_path} ({bytes_written} bytes, model={self._model})"
        )
        return VideoGenerationResult(
            success=True, dry_run=False, provider=self.provider_name,
            scene_id=request.scene_id, shot_id=request.shot_id,
            external_job_id=external_job_id, started_at=started_at, finished_at=datetime.now(UTC),
        )

    def check_status(self, external_job_id: str) -> VideoGenerationStatus:
        """Standalone poll of one operation by name - unused by the V2/V3
        controller (generate() does its own polling internally, SS25.8) but
        kept for interface completeness and any future manual-polling caller."""
        try:
            from google.genai import types
            client = self._get_client()
            operation = client.operations.get(types.GenerateVideosOperation(name=external_job_id))
        except Exception as exc:
            return VideoGenerationStatus(
                status="failed", external_job_id=external_job_id, detail=_describe_exception(exc),
            )
        if not operation.done:
            return VideoGenerationStatus(status="generating", external_job_id=external_job_id)
        if operation.error:
            return VideoGenerationStatus(
                status="failed", external_job_id=external_job_id,
                detail=_describe_exception_dict(operation.error),
            )
        return VideoGenerationStatus(status="succeeded", external_job_id=external_job_id, progress_pct=100.0)

    def _poll_until_done(self, client, operation, options):
        """Polls client.operations.get(operation) on a fixed interval, never
        a busy loop (a plain time.sleep between checks). Bounded by both
        max_poll_attempts and, independently, a wall-clock
        options.timeout_seconds ceiling - whichever is hit first ends the
        job. Returns (final_operation, timeout_error_message_or_None)."""
        deadline = time.monotonic() + options.timeout_seconds if options.timeout_seconds else None
        attempts = 0
        while not operation.done:
            if attempts >= options.max_poll_attempts:
                return operation, f"generation timed out after {attempts} poll attempts"
            if deadline is not None and time.monotonic() >= deadline:
                return operation, f"generation timed out after {options.timeout_seconds}s"
            time.sleep(options.poll_interval_seconds)
            attempts += 1
            try:
                operation = client.operations.get(operation)
            except Exception as exc:
                return operation, _describe_exception(exc)
        return operation, None

    def _save_generated_video(self, video, output_path: Path) -> int:
        """video_bytes may already be populated (e.g. a test double, or a
        non-Gemini-Developer-API backend); only fall back to a streamed
        download of video.uri when it isn't - never re-download something
        already in hand."""
        if video.video_bytes:
            output_path.write_bytes(video.video_bytes)
            return len(video.video_bytes)
        if not video.uri:
            raise ValueError("generated video has neither video_bytes nor a download uri")
        return self._downloader(video.uri, output_path)

    def _default_downloader(self, uri: str, output_path: Path) -> int:
        """Streams the clip to disk in fixed-size chunks - see module
        docstring for why this bypasses client.files.download(). Downloads
        to a `.part` sibling file first and renames only once complete, so a
        connection failure mid-stream never leaves a truncated file at the
        final path for postflight to mistakenly probe."""
        headers = {"x-goog-api-key": self._api_key}
        tmp_path = output_path.with_name(output_path.name + ".part")
        bytes_written = 0
        try:
            with httpx.stream(
                "GET", uri, headers=headers, timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True,
            ) as response:
                response.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                        f.write(chunk)
                        bytes_written += len(chunk)
            os.replace(tmp_path, output_path)
            return bytes_written
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def _failure(
        self, request: VideoGenerationRequest, started_at: datetime,
        external_job_id: Optional[str], error: str, error_type: str,
    ) -> VideoGenerationResult:
        logger.error(
            f"[google_veo provider] generation failed for scene {request.scene_id} "
            f"shot {request.shot_id} ({error_type}): {error}"
        )
        return VideoGenerationResult(
            success=False, dry_run=False, provider=self.provider_name,
            scene_id=request.scene_id, shot_id=request.shot_id,
            external_job_id=external_job_id, started_at=started_at, finished_at=datetime.now(UTC),
            error=error, error_type=error_type,
        )


def _describe_exception_dict(error: dict) -> str:
    """operation.error is a plain dict (google.genai.types.Operation.error),
    not an exception - rendered the same truncated, safe way."""
    return str(error)[:2000]

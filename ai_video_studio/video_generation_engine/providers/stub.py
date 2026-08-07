"""
Zero-cost local video generation provider (ARCHITECTURE.md SS25.16, Milestone
V2: Video Generation Engine Foundation). Reuses ffmpeg's own lavfi color
source plus a drawtext overlay - the same synthetic-source technique
execution_engine.command_builder already uses for a shot Asset Validation
tolerated as missing (a black-frame lavfi input) - to produce a deterministic
placeholder .mp4 clip without any network call, credential, or paid quota.

Registered under "stub" (SS25.16) - a non-default provider name:
VideoGenerationOptions.provider still defaults to "google_veo"
(shared_core/contracts/video_generation.py), so a bare-default run never
silently reaches this instead of a real provider; a caller must pass
options.provider="stub" explicitly.

authenticate() always reports availability conditioned only on ffmpeg itself
being on PATH - there is no external credential of any kind to resolve.
generate() shells out to a single real ffmpeg subprocess, synchronously -
there is no async job to poll, so check_status() reports an immediate
terminal status for shape symmetry with a real async provider, not because
polling means anything here.

Determinism: the ffmpeg invocation fixes every source of run-to-run
variation ffmpeg itself controls (-fflags +bitexact -flags:v +bitexact
-map_metadata -1, no wall-clock-derived content) - two generate() calls for
the same shot/options produce byte-identical output files, verified in
tests/test_video_generation_stub_provider.py.

Deliberately does not import execution_engine (SS25.1 rule 1): the small
resolution parser and duration formatter this module needs duplicate
execution_engine.filter_graph_builder.parse_resolution and
execution_engine.ffmpeg_format.format_seconds rather than import them - the
same accepted-duplication tradeoff already made for ffprobe_client.py in
this package.
"""

import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from shared_core.contracts.video_generation import (
    ProviderInfo,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationStatus,
)
from utils.logger import get_logger
from video_generation_engine.prompt_builder import build_video_prompt
from video_generation_engine.providers.base import VideoGenerationProvider

logger = get_logger("video_generation_engine.providers.stub")

DEFAULT_RESOLUTION = "1280x720"
GENERATION_TIMEOUT_SECONDS = 60
BACKGROUND_COLOR = "0x1a1a2e"
TEXT_COLOR = "white"
FONT_SIZE = 28

_RESOLUTION_RE = re.compile(r"^(\d+)x(\d+)$")

# A short cross-platform search for a usable font file: a plain drawtext
# `font=` name (relying on fontconfig to resolve it) is unreliable on a
# Windows ffmpeg build with no fontconfig cache configured, even one
# compiled with --enable-fontconfig, so an explicit fontfile is preferred
# whenever one of these common paths exists.
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _parse_resolution(resolution: str) -> Tuple[int, int]:
    match = _RESOLUTION_RE.match(resolution.strip())
    if not match:
        raise ValueError(f"Invalid resolution '{resolution}' - expected WIDTHxHEIGHT, e.g. '1280x720'")
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid resolution '{resolution}' - width and height must be positive")
    return width, height


def _format_seconds(value: float) -> str:
    """Trims trailing zeros so 2.0 -> '2', 2.5 -> '2.5' - ffmpeg accepts both."""
    return f"{value:g}"


def _resolve_font_path() -> Optional[str]:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _escape_for_drawtext(text: str) -> str:
    """ffmpeg filter option values use ':' as an option separator, "'" for
    quoting, and '\\' as an escape character - a Windows path's drive-letter
    colon and the overlay text (which embeds no untrusted input, only
    scene/shot integers and a formatted duration, but is escaped on
    principle) must not be misread as filter syntax."""
    return text.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _label_text(request: VideoGenerationRequest) -> str:
    duration = _format_seconds(request.shot_prompt.duration_seconds)
    return f"PLACEHOLDER\nScene {request.scene_id} Shot {request.shot_id}\n{duration}s"


class StubProvider(VideoGenerationProvider):
    provider_name = "stub"

    def __init__(self, *, ffmpeg_path: str = "ffmpeg"):
        self._ffmpeg_path = ffmpeg_path

    def authenticate(self) -> ProviderInfo:
        resolved = shutil.which(self._ffmpeg_path)
        return ProviderInfo(
            provider=self.provider_name,
            available=resolved is not None,
            account_label="local-stub",
            detail=None if resolved else f"'{self._ffmpeg_path}' not found on PATH",
        )

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        started_at = datetime.now(UTC)
        external_job_id = f"stub-{uuid.uuid4()}"

        try:
            width, height = _parse_resolution(request.options.resolution or DEFAULT_RESOLUTION)
        except ValueError as exc:
            return self._failure(request, started_at, external_job_id, str(exc), "generation_failed")

        output_dir = Path(request.output_dir)
        output_path = output_dir / f"scene_{request.scene_id}_shot_{request.shot_id}.mp4"

        # Invoked for parity with a real provider (the composed prompt is
        # what a real adapter would actually send) even though the stub's
        # own visible output is a fixed drawtext overlay, not a rendering
        # of the prompt text itself.
        build_video_prompt(request.shot_prompt, request.options)

        argv = self._build_argv(
            output_path=output_path, width=width, height=height, fps=request.options.fps,
            duration=request.shot_prompt.duration_seconds, label_text=_label_text(request),
        )

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=GENERATION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return self._failure(
                request, started_at, external_job_id,
                f"stub generation timed out after {GENERATION_TIMEOUT_SECONDS}s", "timeout",
            )
        except OSError as exc:
            return self._failure(request, started_at, external_job_id, f"failed to start ffmpeg: {exc}", "generation_failed")

        if proc.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            error = (proc.stderr or "stub generation produced no output file")[-2000:]
            return self._failure(request, started_at, external_job_id, error, "generation_failed")

        logger.info(
            f"[stub provider] generated placeholder clip for scene {request.scene_id} "
            f"shot {request.shot_id}: {output_path}"
        )
        return VideoGenerationResult(
            success=True, dry_run=False, provider=self.provider_name,
            scene_id=request.scene_id, shot_id=request.shot_id,
            external_job_id=external_job_id, started_at=started_at, finished_at=datetime.now(UTC),
        )

    def check_status(self, external_job_id: str) -> VideoGenerationStatus:
        """generate() is synchronous - by the time it returns, the job is
        already terminal. This exists only so StubProvider fully satisfies
        VideoGenerationProvider's shape; nothing in this package calls it
        for a stub-generated job."""
        return VideoGenerationStatus(status="succeeded", external_job_id=external_job_id, progress_pct=100.0)

    def _build_argv(
        self, *, output_path: Path, width: int, height: int, fps: int, duration: float, label_text: str
    ) -> List[str]:
        vf_parts = []
        font_path = _resolve_font_path()
        if font_path:
            escaped_font = _escape_for_drawtext(font_path)
            escaped_text = _escape_for_drawtext(label_text)
            vf_parts.append(
                f"drawtext=fontfile='{escaped_font}':text='{escaped_text}':"
                f"x=(w-text_w)/2:y=(h-text_h)/2:fontcolor={TEXT_COLOR}:fontsize={FONT_SIZE}:line_spacing=8"
            )
        else:
            logger.warning("[stub provider] no usable font found - placeholder clip will have no text overlay")

        argv = [
            self._ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"color=c={BACKGROUND_COLOR}:s={width}x{height}:d={_format_seconds(duration)}:r={fps}",
        ]
        if vf_parts:
            argv.extend(["-vf", ",".join(vf_parts)])
        argv.extend([
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1",
            str(output_path),
        ])
        return argv

    def _failure(
        self, request: VideoGenerationRequest, started_at: datetime, external_job_id: str, error: str, error_type: str
    ) -> VideoGenerationResult:
        return VideoGenerationResult(
            success=False, dry_run=False, provider=self.provider_name,
            scene_id=request.scene_id, shot_id=request.shot_id,
            external_job_id=external_job_id, started_at=started_at, finished_at=datetime.now(UTC),
            error=error, error_type=error_type,
        )

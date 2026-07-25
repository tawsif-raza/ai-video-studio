"""
Read-only ffprobe boundary - the postflight companion to ffmpeg_detector.
Probes an already-rendered file's actual duration and stream properties; it
never writes anything and never judges whether those properties are
acceptable (that's postflight.validate_render's job, kept pure and separate,
exactly like ffmpeg_detector reports availability as data and lets the
controller decide what's fatal).
"""

import json
import shutil
import subprocess
from typing import Optional

from shared_core.contracts.render import ProbedMedia

PROBE_TIMEOUT_SECONDS = 30


def probe(path: str, ffprobe_path: str = "ffprobe") -> Optional[ProbedMedia]:
    """Returns None whenever the file's real properties can't be determined -
    ffprobe missing from PATH, a non-zero exit, unparseable output, or a
    timeout/OS error. postflight.validate_render treats a None probe as an
    unconditional validation failure: a file that can't even be probed cannot
    be verified, so it cannot pass."""
    resolved = shutil.which(ffprobe_path)
    if resolved is None:
        return None

    try:
        proc = subprocess.run(
            [resolved, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if proc.returncode != 0:
        return None

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None

    return _parse_probe_json(data)


def _parse_probe_json(data: dict) -> ProbedMedia:
    duration = _safe_float(data.get("format", {}).get("duration"))

    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    video_fps = None
    if video_stream and video_stream.get("r_frame_rate"):
        video_fps = _parse_frame_rate(video_stream["r_frame_rate"])

    return ProbedMedia(
        duration_seconds=duration,
        has_video_stream=video_stream is not None,
        video_width=video_stream.get("width") if video_stream else None,
        video_height=video_stream.get("height") if video_stream else None,
        video_fps=video_fps,
        video_codec=video_stream.get("codec_name") if video_stream else None,
        has_audio_stream=audio_stream is not None,
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
    )


def _safe_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_frame_rate(raw: str) -> Optional[float]:
    """ffprobe reports frame rate as a "num/den" fraction string, e.g. '30/1'."""
    try:
        num_str, _, den_str = raw.partition("/")
        num, den = float(num_str), float(den_str or 1)
        return num / den if den else None
    except (ValueError, ZeroDivisionError):
        return None

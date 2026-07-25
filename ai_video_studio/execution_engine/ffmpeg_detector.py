"""
Detects the ffmpeg binary. This is a boundary module (it shells out), but a
read-only one: it only asks ffmpeg for its version, never touches media. It
reports availability as data (FFmpegInfo) and never raises - the controller
decides that an unavailable binary is fatal (ExecutionEnvironmentError), so
this stays trivially mockable in tests.
"""

import shutil
import subprocess
from typing import Optional

from shared_core.contracts.render import FFmpegInfo

VERSION_PROBE_TIMEOUT_SECONDS = 10


def _parse_version(first_line: str) -> Optional[str]:
    """`ffmpeg version 6.1.1 Copyright ...` -> `6.1.1`. Returns None for any
    line that doesn't match the expected shape rather than guessing."""
    parts = first_line.split()
    if len(parts) >= 3 and parts[0] == "ffmpeg" and parts[1] == "version":
        return parts[2]
    return None


def detect_ffmpeg(ffmpeg_path: str = "ffmpeg") -> FFmpegInfo:
    """Resolves the binary on PATH and confirms it runs `-version` cleanly.
    Any failure - not on PATH, non-zero exit, or the process erroring/timing
    out - is reported as available=False rather than raised."""
    resolved = shutil.which(ffmpeg_path)
    if resolved is None:
        return FFmpegInfo(available=False)

    try:
        proc = subprocess.run(
            [resolved, "-version"],
            capture_output=True,
            text=True,
            timeout=VERSION_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return FFmpegInfo(available=False, path=resolved)

    if proc.returncode != 0:
        return FFmpegInfo(available=False, path=resolved)

    first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    return FFmpegInfo(
        available=True,
        path=resolved,
        version=_parse_version(first_line),
        raw_version_line=first_line or None,
    )

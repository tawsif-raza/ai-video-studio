"""
Pure execution boundary for the FFmpeg Execution Engine - runs an already-
built, immutable FFmpegCommandSpec as a subprocess and returns a structured
RenderResult. This is the only module in the Execution Engine that spawns a
process or writes render output. It contains no planning logic of its own: it
never inspects an EditingPlan, Timeline, SubtitlePlan, or MusicPlan, and it
never decides what the command should be, whether to run at all (--dry-run is
decided by the controller, which simply never calls this module), or when a
project's state should advance. It only runs the command it is given and
reports what happened.

Output is written atomically: ffmpeg is pointed at a temporary path next to
the spec's real output_path, and that temp file is renamed to the real path
only after the process exits 0 and the file exists with non-zero size. Any
failure - non-zero exit, a timeout, or the process never starting - deletes
any partial temp file; a file at output_path is written if and only if
execute() returns success=True, so nothing downstream can ever mistake a
partial/failed attempt for a finished render.

execute() never raises. A failed render is a reportable runtime outcome
returned as RenderResult(success=False, ...), exactly like Asset Validation's
is_valid=False - not a Python exception.

Scope note: this module verifies only that the subprocess produced a file - it
does not probe its duration or streams. That deeper content verification is a
deliberately separate, later stage, and the VIDEO_RENDERED project-state
transition is gated on it, not on this module's success alone (a later
milestone; see ExecutionEngineController).
"""

import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from shared_core.contracts.render import FFmpegCommandSpec, RenderResult

# How much of ffmpeg's stderr to keep on failure - enough to diagnose a
# problem without embedding an unbounded log in the result.
STDERR_TAIL_CHARS = 4000


def execute(
    command_spec: FFmpegCommandSpec,
    *,
    ffmpeg_path: str = "ffmpeg",
    timeout_seconds: Optional[int] = None,
) -> RenderResult:
    """Runs command_spec as a real ffmpeg subprocess, writing to a temp file
    that is atomically renamed to command_spec.output_path only on verified
    success."""
    started_at = datetime.now(UTC)
    start = time.monotonic()

    final_output = Path(command_spec.output_path)
    # The temp name must still END in the real extension (video.part.mp4, not
    # video.mp4.part) - ffmpeg infers the container/muxer from the output
    # filename's suffix, and a ".part" suffix makes it unable to choose one.
    temp_output = final_output.with_name(f"{final_output.stem}.part{final_output.suffix}")
    final_output.parent.mkdir(parents=True, exist_ok=True)
    argv = _argv_with_temp_output(command_spec, ffmpeg_path, temp_output)

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _cleanup(temp_output)
        return _failure(
            started_at, time.monotonic() - start,
            error=f"FFmpeg timed out after {timeout_seconds}s",
            error_type="timeout",
            stderr_tail=_tail(exc.stderr if isinstance(exc.stderr, str) else None),
        )
    except OSError as exc:
        _cleanup(temp_output)
        return _failure(
            started_at, time.monotonic() - start,
            error=f"Failed to start ffmpeg: {exc}",
            error_type="spawn_error",
        )

    duration = time.monotonic() - start

    if proc.returncode != 0:
        _cleanup(temp_output)
        return _failure(
            started_at, duration,
            error=f"ffmpeg exited with code {proc.returncode}",
            error_type="ffmpeg_failed",
            exit_code=proc.returncode,
            stderr_tail=_tail(proc.stderr),
        )

    if not temp_output.is_file() or temp_output.stat().st_size == 0:
        _cleanup(temp_output)
        return _failure(
            started_at, duration,
            error="ffmpeg exited successfully but produced no output file",
            error_type="ffmpeg_failed",
            exit_code=proc.returncode,
            stderr_tail=_tail(proc.stderr),
        )

    temp_output.replace(final_output)

    return RenderResult(
        success=True,
        dry_run=False,
        output_path=str(final_output),
        exit_code=proc.returncode,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        duration_seconds=duration,
    )


def _argv_with_temp_output(spec: FFmpegCommandSpec, ffmpeg_path: str, temp_output: Path) -> List[str]:
    argv = spec.to_argv(ffmpeg_path)
    assert argv[-1] == spec.output_path, "FFmpegCommandSpec.to_argv() must end with output_path"
    argv[-1] = str(temp_output)
    return argv


def _cleanup(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _tail(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return text[-STDERR_TAIL_CHARS:]


def _failure(
    started_at: datetime, duration: float, *, error: str, error_type: str,
    exit_code: Optional[int] = None, stderr_tail: Optional[str] = None,
) -> RenderResult:
    return RenderResult(
        success=False,
        dry_run=False,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        duration_seconds=duration,
        error=error,
        error_type=error_type,
        stderr_tail=stderr_tail,
    )

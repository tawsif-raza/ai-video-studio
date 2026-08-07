"""
Pure postflight media-quality validation (ARCHITECTURE.md SS25.6) - given an
already-probed generated clip (ffprobe_client.probe's job) and the request's
own expected profile (the shot's planned duration, the request's aspect
ratio), compares actual vs. expected and produces a structured
VideoGenerationValidationReport. No filesystem access, no subprocess - a
typed function of typed data to a typed report, exactly like
execution_engine.postflight.validate_render, whose "None probe is an
unconditional failure" handling this mirrors directly.

is_valid=True is the only thing that should ever be treated as "this clip is
trustworthy" - VideoGenerationResult.success=True means only that the
provider accepted and completed the job, never this.
"""

from typing import List, Optional

from shared_core.contracts.render import ProbedMedia
from shared_core.contracts.video_generation import (
    VideoGenerationRequest,
    VideoGenerationValidationCheck,
    VideoGenerationValidationReport,
)

# Generous relative to execution_engine's DURATION_TOLERANCE_SECONDS (0.5s):
# a compiled render's duration is a deterministic sum of exact segment
# timings, while a generated clip's real length is whatever the provider
# (or, for the local stub, ffmpeg's own lavfi/encoder rounding) actually
# produced for a requested duration - still expected to be close, not exact.
DURATION_TOLERANCE_SECONDS = 1.0

# Relative tolerance on width/height ratio vs. the requested aspect_ratio
# string (e.g. "9:16"), absorbing integer-pixel-dimension rounding.
ASPECT_RATIO_TOLERANCE = 0.05


def _check(name: str, passed: bool, expected: str, actual: str) -> VideoGenerationValidationCheck:
    return VideoGenerationValidationCheck(name=name, passed=passed, expected=expected, actual=actual)


def _parse_aspect_ratio(aspect_ratio: str) -> Optional[float]:
    width_str, _, height_str = aspect_ratio.partition(":")
    try:
        width, height = float(width_str), float(height_str)
        return width / height if height else None
    except ValueError:
        return None


def validate_generated_clip(
    probed: Optional[ProbedMedia], request: VideoGenerationRequest, *, output_path: str
) -> VideoGenerationValidationReport:
    """Builds the postflight verdict. A None probe (ffprobe unavailable, the
    file unreadable/corrupt) is an unconditional failure - there is nothing
    to compare, so nothing can pass."""
    if probed is None:
        return VideoGenerationValidationReport(
            is_valid=False,
            checks=[_check("probe", False, "a readable generated clip", "unprobeable")],
            probed=None,
            output_path=output_path,
        )

    checks: List[VideoGenerationValidationCheck] = [
        _check("video_stream", probed.has_video_stream, "present", "present" if probed.has_video_stream else "absent"),
    ]

    expected_duration = request.shot_prompt.duration_seconds
    duration_ok = (
        probed.duration_seconds is not None
        and abs(probed.duration_seconds - expected_duration) <= DURATION_TOLERANCE_SECONDS
    )
    checks.append(_check(
        "duration", duration_ok,
        f"{expected_duration}s (+/-{DURATION_TOLERANCE_SECONDS}s)", f"{probed.duration_seconds}s",
    ))

    expected_ratio = _parse_aspect_ratio(request.options.aspect_ratio)
    if probed.has_video_stream and expected_ratio is not None and probed.video_width and probed.video_height:
        actual_ratio = probed.video_width / probed.video_height
        ratio_ok = abs(actual_ratio - expected_ratio) <= ASPECT_RATIO_TOLERANCE * expected_ratio
        checks.append(_check(
            "aspect_ratio", ratio_ok,
            request.options.aspect_ratio, f"{probed.video_width}x{probed.video_height}",
        ))

    return VideoGenerationValidationReport(
        is_valid=all(check.passed for check in checks),
        checks=checks,
        probed=probed,
        output_path=output_path,
    )

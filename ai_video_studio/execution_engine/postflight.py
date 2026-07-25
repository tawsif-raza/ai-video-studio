"""
Pure postflight media-quality validation (Milestone 8.4) - the deliberately
separate stage that RenderResult.success alone was never meant to satisfy
(see ffmpeg_executor's module docstring: "this module verifies only that the
subprocess produced a file - it does not probe its duration or streams").
Given an already-probed rendered file (ffprobe_client.probe's job) and the
render's own expected profile (the editing plan's total duration, the
render's requested resolution/fps), this module compares actual vs expected
and produces a structured RenderValidationReport. No filesystem access, no
subprocess - a typed function of typed data to a typed report, exactly like
command_builder and filter_graph_builder.

This is the ONLY gate for the VIDEO_RENDERED project-state transition:
ExecutionEngineController advances state if and only if
RenderValidationReport.is_valid is True.
"""

from typing import List, Optional

from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.render import (
    ProbedMedia,
    RenderOptions,
    RenderValidationCheck,
    RenderValidationReport,
)

# Tolerances wide enough to absorb ordinary encoder/muxer rounding (keyframe
# alignment, container timestamp granularity) while still catching a
# genuinely wrong render (a missing scene, a broken filter graph offset).
DURATION_TOLERANCE_SECONDS = 0.5
FPS_TOLERANCE = 0.1


def _parse_resolution(resolution: str) -> Optional[tuple]:
    width_str, _, height_str = resolution.partition("x")
    try:
        return int(width_str), int(height_str)
    except ValueError:
        return None


def _check(name: str, passed: bool, expected: str, actual: str) -> RenderValidationCheck:
    return RenderValidationCheck(name=name, passed=passed, expected=expected, actual=actual)


def validate_render(
    probed: Optional[ProbedMedia], editing_plan: EditingPlan, options: RenderOptions, *, output_path: str
) -> RenderValidationReport:
    """Builds the postflight verdict. A None probe (ffprobe unavailable, the
    file unreadable/corrupt) is an unconditional failure - there is nothing to
    compare, so nothing can pass."""
    if probed is None:
        return RenderValidationReport(
            is_valid=False,
            checks=[_check(
                "probe", False, "a readable rendered file", "unprobeable",
            )],
            probed=None,
            output_path=output_path,
        )

    checks: List[RenderValidationCheck] = [
        _check("video_stream", probed.has_video_stream, "present", "present" if probed.has_video_stream else "absent"),
        _check("audio_stream", probed.has_audio_stream, "present", "present" if probed.has_audio_stream else "absent"),
    ]

    expected_resolution = _parse_resolution(options.resolution)
    if probed.has_video_stream and expected_resolution is not None:
        expected_width, expected_height = expected_resolution
        resolution_ok = probed.video_width == expected_width and probed.video_height == expected_height
        checks.append(_check(
            "resolution", resolution_ok,
            f"{expected_width}x{expected_height}", f"{probed.video_width}x{probed.video_height}",
        ))

        fps_ok = probed.video_fps is not None and abs(probed.video_fps - options.fps) <= FPS_TOLERANCE
        checks.append(_check("fps", fps_ok, str(options.fps), str(probed.video_fps)))

    duration_ok = (
        probed.duration_seconds is not None
        and abs(probed.duration_seconds - editing_plan.total_duration_seconds) <= DURATION_TOLERANCE_SECONDS
    )
    checks.append(_check(
        "duration", duration_ok,
        f"{editing_plan.total_duration_seconds}s (+/-{DURATION_TOLERANCE_SECONDS}s)",
        f"{probed.duration_seconds}s",
    ))

    return RenderValidationReport(
        is_valid=all(check.passed for check in checks),
        checks=checks,
        probed=probed,
        output_path=output_path,
    )

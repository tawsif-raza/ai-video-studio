from execution_engine.postflight import (
    DURATION_TOLERANCE_SECONDS,
    FPS_TOLERANCE,
    validate_render,
)
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.render import ProbedMedia, RenderOptions


def _plan(total_duration_seconds=20.0):
    return EditingPlan(editing_plan_id="ep1", total_duration_seconds=total_duration_seconds)


def _probe(**overrides):
    defaults = dict(
        duration_seconds=20.0, has_video_stream=True, video_width=1920, video_height=1080,
        video_fps=30.0, video_codec="h264", has_audio_stream=True, audio_codec="aac",
    )
    defaults.update(overrides)
    return ProbedMedia(**defaults)


def _options(**overrides):
    defaults = dict(resolution="1920x1080", fps=30)
    defaults.update(overrides)
    return RenderOptions(**defaults)


def test_matching_media_passes_every_check():
    report = validate_render(_probe(), _plan(), _options(), output_path="/renders/video.mp4")

    assert report.is_valid is True
    assert all(check.passed for check in report.checks)
    names = {check.name for check in report.checks}
    assert {"video_stream", "audio_stream", "resolution", "fps", "duration"} == names


def test_none_probe_is_unconditional_failure():
    report = validate_render(None, _plan(), _options(), output_path="/renders/video.mp4")

    assert report.is_valid is False
    assert report.probed is None
    assert len(report.checks) == 1
    assert report.checks[0].name == "probe"
    assert report.checks[0].passed is False


def test_missing_video_stream_fails():
    report = validate_render(
        _probe(has_video_stream=False, video_width=None, video_height=None, video_fps=None),
        _plan(), _options(), output_path="/renders/video.mp4",
    )

    video_check = next(c for c in report.checks if c.name == "video_stream")
    assert video_check.passed is False
    assert report.is_valid is False
    # no video stream means resolution/fps can't be meaningfully checked either
    assert not any(c.name in ("resolution", "fps") for c in report.checks)


def test_missing_audio_stream_fails():
    report = validate_render(_probe(has_audio_stream=False, audio_codec=None), _plan(), _options(),
                             output_path="/renders/video.mp4")

    audio_check = next(c for c in report.checks if c.name == "audio_stream")
    assert audio_check.passed is False
    assert report.is_valid is False


def test_wrong_resolution_fails():
    report = validate_render(_probe(video_width=1280, video_height=720), _plan(), _options(),
                             output_path="/renders/video.mp4")

    resolution_check = next(c for c in report.checks if c.name == "resolution")
    assert resolution_check.passed is False
    assert resolution_check.expected == "1920x1080"
    assert resolution_check.actual == "1280x720"
    assert report.is_valid is False


def test_wrong_fps_outside_tolerance_fails():
    report = validate_render(_probe(video_fps=24.0), _plan(), _options(), output_path="/renders/video.mp4")

    fps_check = next(c for c in report.checks if c.name == "fps")
    assert fps_check.passed is False
    assert report.is_valid is False


def test_fps_within_tolerance_passes():
    report = validate_render(
        _probe(video_fps=30.0 + FPS_TOLERANCE / 2), _plan(), _options(), output_path="/renders/video.mp4"
    )

    fps_check = next(c for c in report.checks if c.name == "fps")
    assert fps_check.passed is True


def test_duration_within_tolerance_passes():
    report = validate_render(
        _probe(duration_seconds=20.0 + DURATION_TOLERANCE_SECONDS / 2),
        _plan(total_duration_seconds=20.0), _options(), output_path="/renders/video.mp4",
    )

    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed is True


def test_duration_outside_tolerance_fails():
    report = validate_render(
        _probe(duration_seconds=20.0 + DURATION_TOLERANCE_SECONDS * 3),
        _plan(total_duration_seconds=20.0), _options(), output_path="/renders/video.mp4",
    )

    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed is False
    assert report.is_valid is False


def test_missing_probed_duration_fails():
    report = validate_render(_probe(duration_seconds=None), _plan(), _options(), output_path="/renders/video.mp4")

    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed is False


def test_output_path_and_probed_media_recorded_on_report():
    probed = _probe()
    report = validate_render(probed, _plan(), _options(), output_path="/renders/video.mp4")

    assert report.output_path == "/renders/video.mp4"
    assert report.probed == probed


def test_single_failing_check_fails_whole_report():
    # everything matches except duration - is_valid must still be False
    report = validate_render(
        _probe(duration_seconds=1.0), _plan(total_duration_seconds=20.0), _options(),
        output_path="/renders/video.mp4",
    )

    assert report.is_valid is False
    passing = [c.name for c in report.checks if c.passed]
    assert "video_stream" in passing and "resolution" in passing  # others still individually correct

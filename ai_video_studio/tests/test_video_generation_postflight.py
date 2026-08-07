from shared_core.contracts.prompt_set import ShotPrompt
from shared_core.contracts.render import ProbedMedia
from shared_core.contracts.video_generation import VideoGenerationOptions, VideoGenerationRequest
from video_generation_engine.postflight import validate_generated_clip


def _request(*, duration_seconds=5, **option_overrides):
    shot_prompt = ShotPrompt(
        scene_id=1, shot_id=1, duration_seconds=duration_seconds,
        image_prompt="x" * 50, video_motion_prompt="camera pans across the scene slowly",
    )
    defaults = dict(aspect_ratio="9:16")
    defaults.update(option_overrides)
    return VideoGenerationRequest(
        shot_prompt=shot_prompt, scene_id=1, shot_id=1, output_dir="/media/video",
        options=VideoGenerationOptions(**defaults),
    )


def _probe(**overrides):
    defaults = dict(
        duration_seconds=5.0, has_video_stream=True, video_width=720, video_height=1280,
        video_fps=30.0, video_codec="h264",
    )
    defaults.update(overrides)
    return ProbedMedia(**defaults)


def test_matching_clip_passes_every_check():
    report = validate_generated_clip(_probe(), _request(), output_path="/media/video/x.mp4")

    assert report.is_valid is True
    assert {"video_stream", "duration", "aspect_ratio"} == {c.name for c in report.checks}


def test_none_probe_is_unconditional_failure():
    report = validate_generated_clip(None, _request(), output_path="/media/video/x.mp4")

    assert report.is_valid is False
    assert report.probed is None
    assert len(report.checks) == 1
    assert report.checks[0].name == "probe"


def test_missing_video_stream_fails():
    probe = _probe(has_video_stream=False, video_width=None, video_height=None)

    report = validate_generated_clip(probe, _request(), output_path="/x.mp4")

    assert report.is_valid is False
    failed = {c.name for c in report.checks if not c.passed}
    assert "video_stream" in failed


def test_duration_within_tolerance_passes():
    report = validate_generated_clip(_probe(duration_seconds=5.9), _request(duration_seconds=5), output_path="/x.mp4")
    assert report.is_valid is True


def test_duration_outside_tolerance_fails():
    report = validate_generated_clip(_probe(duration_seconds=10.0), _request(duration_seconds=5), output_path="/x.mp4")
    failed = {c.name for c in report.checks if not c.passed}
    assert "duration" in failed
    assert report.is_valid is False


def test_aspect_ratio_mismatch_fails():
    # 720x1280 is 9:16 - a 1920x1080 (16:9) probe should fail an aspect_ratio="9:16" request.
    report = validate_generated_clip(_probe(video_width=1920, video_height=1080), _request(), output_path="/x.mp4")
    failed = {c.name for c in report.checks if not c.passed}
    assert "aspect_ratio" in failed


def test_aspect_ratio_check_skipped_when_no_video_stream():
    probe = _probe(has_video_stream=False, video_width=None, video_height=None)
    report = validate_generated_clip(probe, _request(), output_path="/x.mp4")
    assert "aspect_ratio" not in {c.name for c in report.checks}

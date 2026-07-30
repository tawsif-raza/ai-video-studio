"""Regression coverage for both Release-Prep rendering-reliability defects,
found during D4 cloud validation:

1. A multi-scene render at 1920x1080 with libx264's "medium" preset was
   killed by SIGKILL under the deployment's real 1GB/2vCPU container
   (reproduced directly against that limit via `docker run --memory=1g
   --cpus=2`, outside this suite - not reproducible here since ordinary
   dev/CI machines have far more headroom, which is exactly why it shipped
   unnoticed). Fixed by changing the default preset to "fast" everywhere it
   is mirrored (shared_core/contracts/render.py, web_api/models.py,
   render_app.py); this file's job is to guard against a regression back to a
   heavier default, not to reproduce the OOM itself.
2. EditingPlan.total_duration_seconds held the Timeline's raw, contiguous sum
   of shot durations, but any project with a scene-boundary crossfade renders
   shorter than that sum (a crossfade overlaps, and so shrinks, the two clips
   either side of it) - so postflight validation, which compares the two,
   failed by design for every multi-scene project. Fixed in
   agents/editing_planner/validator.py via
   shared_core.contracts.editing_plan.compute_final_duration_seconds.

This test renders a real single-scene and a real multi-scene (crossfade)
edit, at both 720p and 1080p, through the actual command_builder /
ffmpeg_executor / postflight modules with real ffmpeg - the only way to
confirm the probed duration of an actual rendered file agrees with what
Editing Planning now computes, closing the loop the unit tests
(tests/shared_core/test_editing_plan_duration.py, test_editing_planner.py)
can't reach on their own.
"""

import subprocess

import pytest

from execution_engine.command_builder import build_command, validate_render_request
from execution_engine.ffmpeg_detector import detect_ffmpeg
from execution_engine.ffmpeg_executor import execute
from execution_engine.ffprobe_client import probe
from execution_engine.postflight import validate_render
from execution_engine.preflight import verify_media_exists
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingSegment, compute_final_duration_seconds
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderOptions, RenderRequest
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline

_ffmpeg_info = detect_ffmpeg()

pytestmark = pytest.mark.skipif(not _ffmpeg_info.available, reason="ffmpeg not available on this machine")


def _make_tiny_image(path, color):
    subprocess.run(
        [_ffmpeg_info.path, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=64x64:d=1",
         "-frames:v", "1", str(path), "-loglevel", "error"],
        check=True, timeout=30,
    )


def _make_tiny_audio(path, duration):
    subprocess.run(
        [_ffmpeg_info.path, "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono", "-t", str(duration),
         str(path), "-loglevel", "error"],
        check=True, timeout=30,
    )


def _segment(scene_id, shot_id, path, start, end, *, transition_in, transition_out):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=str(path), asset_type="image",
        start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def _single_scene_segments(img):
    return [_segment(1, 1, img, 0.0, 4.0, transition_in="fade_from_black", transition_out="fade_to_black")]


def _multi_scene_segments(imgs):
    # Same shape as the D4 cloud-validation repro: scene1 -x-> scene2 (two
    # cut-joined shots) -x-> scene3.
    return [
        _segment(1, 1, imgs[0], 0.0, 4.0, transition_in="fade_from_black", transition_out="crossfade"),
        _segment(2, 1, imgs[1], 4.0, 7.0, transition_in="crossfade", transition_out="cut"),
        _segment(2, 2, imgs[2], 7.0, 9.0, transition_in="cut", transition_out="crossfade"),
        _segment(3, 1, imgs[3], 9.0, 13.0, transition_in="crossfade", transition_out="fade_to_black"),
    ]


def _render_and_validate(tmp_path, segments, resolution):
    from shared_core.contracts.editing_plan import EditingPlan

    total = compute_final_duration_seconds(segments)

    # Narration is generated against the plan's own (crossfade-adjusted)
    # target duration in real usage, never against the raw pre-crossfade
    # sum - matching that here matters: ffmpeg's output duration follows
    # whichever mapped stream is longest, so an audio track longer than the
    # shrunk video would mask the very regression this test exists to catch.
    narration = tmp_path / "voice_script.wav"
    _make_tiny_audio(narration, duration=total)
    plan = EditingPlan(
        editing_plan_id="ep-regress", segments=segments, total_duration_seconds=total,
        source_timeline_id="tl1", source_subtitle_plan_id="sp1", source_music_plan_id="mp1",
    )

    request = RenderRequest(
        editing_plan=plan,
        asset_manifest=ValidatedAssetManifest(
            manifest_id="m1", source_prompt_set_id="ps", is_valid=True, narration_audio_path=str(narration),
        ),
        timeline=Timeline(timeline_id="tl1", source_asset_manifest_id="m1"),
        subtitle_plan=SubtitlePlan(subtitle_plan_id="sp1", source_timeline_id="tl1"),
        music_plan=MusicPlan(music_plan_id="mp1", source_timeline_id="tl1"),
        output_dir=str(tmp_path / "out"),
        options=RenderOptions(resolution=resolution),  # uses the shipped default preset ("fast")
    )

    validate_render_request(request)
    verify_media_exists(request)
    spec = build_command(request)

    result = execute(spec, ffmpeg_path=_ffmpeg_info.path, timeout_seconds=60)
    assert result.success, f"render failed: {result.error} / {result.stderr_tail}"

    probed = probe(result.output_path)
    report = validate_render(probed, plan, request.options, output_path=result.output_path)
    return report


@pytest.fixture
def images(tmp_path):
    paths = [tmp_path / f"img{i}.jpg" for i in range(4)]
    colors = ["red", "green", "blue", "yellow"]
    for path, color in zip(paths, colors):
        _make_tiny_image(path, color)
    return paths


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080"])
def test_single_scene_renders_and_validates(tmp_path, images, resolution):
    report = _render_and_validate(tmp_path, _single_scene_segments(images[0]), resolution)

    assert report.is_valid, [c for c in report.checks if not c.passed]
    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080"])
def test_multi_scene_crossfade_renders_and_validates(tmp_path, images, resolution):
    # This is the exact scenario that used to fail postflight's duration
    # check on every run, regardless of resolution or preset - defect 2.
    report = _render_and_validate(tmp_path, _multi_scene_segments(images), resolution)

    assert report.is_valid, [c for c in report.checks if not c.passed]
    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed
    # Sanity: this plan's crossfades really do make it shorter than the raw
    # per-segment sum (13.0s) - otherwise this test would not be exercising
    # the regression at all.
    assert probe(report.output_path).duration_seconds < 13.0

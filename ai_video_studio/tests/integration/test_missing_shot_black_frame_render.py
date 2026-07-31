"""Real-ffmpeg regression coverage for the Release milestone that made Asset
Validation tolerate up to MAX_TOLERATED_MISSING_SHOTS shots with no image or
video at all, rather than blocking is_valid outright for even one missing
shot. A tolerated missing shot is resolved (timeline_planner) to a "black"
TimelineClip/EditingSegment with no real asset_path, and command_builder
synthesizes an `-f lavfi -i color=c=black:s=<w>x<h>:d=<dur>` input for it at
this render's own resolution. This test renders that end to end through real
ffmpeg - not just unit-level contract/argv assertions - to confirm the
synthesized black frame actually produces a valid, correctly-timed video
alongside real image segments, at both 720p and 1080p."""

import subprocess

import pytest

from execution_engine.command_builder import build_command, validate_render_request
from execution_engine.ffmpeg_detector import detect_ffmpeg
from execution_engine.ffmpeg_executor import execute
from execution_engine.ffprobe_client import probe
from execution_engine.postflight import validate_render
from execution_engine.preflight import verify_media_exists
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment, compute_final_duration_seconds
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
        [_ffmpeg_info.path, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(duration),
         str(path), "-loglevel", "error"],
        check=True, timeout=30,
    )


def _image_segment(scene_id, shot_id, path, start, end, *, transition_in, transition_out):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=str(path), asset_type="image",
        start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def _black_segment(scene_id, shot_id, start, end, *, transition_in, transition_out):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=None, asset_type="black",
        start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def _render_and_validate(tmp_path, segments, resolution):
    total = compute_final_duration_seconds(segments)

    narration = tmp_path / "voice_script.wav"
    _make_tiny_audio(narration, duration=total)
    plan = EditingPlan(
        editing_plan_id="ep-black", segments=segments, total_duration_seconds=total,
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
        options=RenderOptions(resolution=resolution),
    )

    validate_render_request(request)
    verify_media_exists(request)  # must not try to stat the black segment's (None) path
    spec = build_command(request)

    result = execute(spec, ffmpeg_path=_ffmpeg_info.path, timeout_seconds=60)
    assert result.success, f"render failed: {result.error} / {result.stderr_tail}"

    probed = probe(result.output_path)
    report = validate_render(probed, plan, request.options, output_path=result.output_path)
    return report


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "img.jpg"
    _make_tiny_image(path, "red")
    return path


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080"])
def test_single_shot_entirely_missing_still_renders_black(tmp_path, resolution):
    # The most tolerant case: the only shot in the whole edit has no asset
    # at all - the entire render is one synthesized black frame.
    segments = [_black_segment(1, 1, 0.0, 4.0, transition_in="fade_from_black", transition_out="fade_to_black")]

    report = _render_and_validate(tmp_path, segments, resolution)

    assert report.is_valid, [c for c in report.checks if not c.passed]


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080"])
def test_middle_shot_missing_among_real_images_still_renders(tmp_path, image, resolution):
    # The realistic case: most shots have real media, one in the middle
    # (within tolerance) doesn't - crossfading into and out of a black frame
    # must still produce a correctly-timed, valid render.
    segments = [
        _image_segment(1, 1, image, 0.0, 4.0, transition_in="fade_from_black", transition_out="crossfade"),
        _black_segment(2, 1, 4.0, 7.0, transition_in="crossfade", transition_out="crossfade"),
        _image_segment(3, 1, image, 7.0, 11.0, transition_in="crossfade", transition_out="fade_to_black"),
    ]

    report = _render_and_validate(tmp_path, segments, resolution)

    assert report.is_valid, [c for c in report.checks if not c.passed]
    duration_check = next(c for c in report.checks if c.name == "duration")
    assert duration_check.passed

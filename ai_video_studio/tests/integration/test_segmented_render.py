"""Real-ffmpeg regression coverage for segmented_renderer.py - the fallback
render strategy for editing plans with many scene-crossfade boundaries
(execution_engine/segmented_renderer.py's module docstring: production
telemetry showed the single-filter_complex path can OOM-kill ffmpeg on a
memory-constrained deployment for a many-scene project, independent of
output resolution). This renders a synthetic 7-scene, 7-shot edit (well
above SEGMENT_CHAIN_THRESHOLD) through real ffmpeg via should_segment's
actual decision and execute_segmented's actual pipeline - not just
unit-level command/offset assertions - confirming the segmented output is
a valid, correctly-timed video indistinguishable in shape from what the
single-pass path would have produced for the same plan."""

import subprocess

import pytest

from execution_engine.command_builder import validate_render_request
from execution_engine.ffmpeg_detector import detect_ffmpeg
from execution_engine.ffprobe_client import probe
from execution_engine.postflight import validate_render
from execution_engine.preflight import verify_media_exists
from execution_engine.segmented_renderer import execute_segmented, should_segment
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment, compute_final_duration_seconds
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderOptions, RenderRequest
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline

_ffmpeg_info = detect_ffmpeg()

pytestmark = pytest.mark.skipif(not _ffmpeg_info.available, reason="ffmpeg not available on this machine")

_COLORS = ["red", "green", "blue", "yellow", "cyan", "magenta", "white"]


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


def _many_scene_segments(tmp_path, num_scenes: int, shot_duration: float = 2.0):
    """One shot per scene (so every scene is its own single-shot chain,
    matching this project's real Editing Planner pattern of cuts within a
    scene / crossfades between scenes), each a distinct tiny solid-color
    image so a human (or an automated frame check) could tell the shots
    apart in the rendered output."""
    segments = []
    t = 0.0
    for i in range(num_scenes):
        scene_id = i + 1
        is_first, is_last = i == 0, i == num_scenes - 1
        image_path = tmp_path / f"scene_{scene_id}_shot_{scene_id}.jpg"
        _make_tiny_image(image_path, _COLORS[i % len(_COLORS)])
        segments.append(EditingSegment(
            scene_id=scene_id, shot_id=scene_id, asset_path=str(image_path), asset_type="image",
            start_time=t, end_time=t + shot_duration, music_cue_scene_id=scene_id,
            transition_in="fade_from_black" if is_first else "crossfade",
            transition_out="fade_to_black" if is_last else "crossfade",
        ))
        t += shot_duration
    return segments


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080"])
def test_many_scene_edit_triggers_segmentation_and_renders_correctly(tmp_path, resolution):
    segments = _many_scene_segments(tmp_path, num_scenes=7)
    narration = tmp_path / "voice_script.wav"
    total = compute_final_duration_seconds(segments)
    _make_tiny_audio(narration, duration=total)

    plan = EditingPlan(
        editing_plan_id="ep-segmented", segments=segments, total_duration_seconds=total,
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

    # This is the real decision execution_engine/controller.py makes - a
    # 7-scene edit must actually route through the segmented path, not
    # silently fall back to the single-pass one.
    assert should_segment(request.editing_plan) is True

    validate_render_request(request)
    verify_media_exists(request)

    result = execute_segmented(request, ffmpeg_path=_ffmpeg_info.path, timeout_seconds=60)
    assert result.success, f"segmented render failed: {result.error} / {result.stderr_tail}"
    assert result.output_path.endswith("video.mp4")

    # No leftover intermediate chain/merge files after a successful render.
    assert not (tmp_path / "out" / ".segments").exists()

    probed = probe(result.output_path)
    report = validate_render(probed, plan, request.options, output_path=result.output_path)
    assert report.is_valid, [c for c in report.checks if not c.passed]


def test_segmented_render_reports_failure_when_a_source_image_is_corrupt(tmp_path):
    """A step failing partway through the pipeline (not just the final
    step) must still surface as an ordinary, reportable RenderResult
    failure - the same 'reportable, not exceptional' contract the
    single-pass path already guarantees."""
    segments = _many_scene_segments(tmp_path, num_scenes=7)
    # Corrupt one of the middle chain's source image so that chain's own
    # ffmpeg process (not the final mux step) is what actually fails.
    corrupt_path = segments[3].asset_path
    with open(corrupt_path, "wb") as f:
        f.write(b"not a real image")

    narration = tmp_path / "voice_script.wav"
    total = compute_final_duration_seconds(segments)
    _make_tiny_audio(narration, duration=total)

    plan = EditingPlan(
        editing_plan_id="ep-corrupt", segments=segments, total_duration_seconds=total,
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
    )

    validate_render_request(request)
    verify_media_exists(request)  # corrupt file still exists on disk, so this passes

    # A corrupt image combined with `-loop 1` can make ffmpeg hang rather
    # than exit non-zero quickly (the same behavior the single-pass path
    # would hit for the same corrupt input, via the same build_segment_input
    # `-loop 1` mechanism) - bound tightly so the test itself stays fast,
    # and accept either reportable failure shape (a quick non-zero exit, or
    # ffmpeg_executor's own TimeoutExpired handling firing instead).
    result = execute_segmented(request, ffmpeg_path=_ffmpeg_info.path, timeout_seconds=5)

    assert result.success is False
    assert result.error_type in ("ffmpeg_failed", "timeout")
    assert not (tmp_path / "out" / "video.mp4").exists()
    assert not (tmp_path / "out" / ".segments").exists()  # cleaned up even on failure

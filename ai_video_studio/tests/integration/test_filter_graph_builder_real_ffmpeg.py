"""
Regression test for the concat/xfade timebase bug discovered during the
AI Video Studio v1.0 end-to-end validation: a multi-segment "cut" chain
(built via ffmpeg's concat filter) sitting immediately next to a crossfade
(xfade) failed with "First input link main timebase (1/30) do not match the
corresponding second input link xfade timebase (1/1000000)" - a real ffmpeg
runtime behavior (concat does not propagate its inputs' timebase to its
output) that no string-only assertion on the compiled filter_complex could
ever catch, which is exactly why it shipped undetected: an existing test
(test_mixed_cut_and_crossfade_within_multi_shot_scenes) builds this precise
graph shape but only asserts on filter names/counts as text.

This test builds the same graph shape and actually runs it through real
ffmpeg, skipped when ffmpeg isn't available - the one deliberate exception
to this project's "real-binary verification is manual, not part of pytest"
convention (ARCHITECTURE.md SS18), justified because this bug class is by
definition invisible to a hermetic, string-only test.
"""

import subprocess

import pytest

from execution_engine.command_builder import GLOBAL_ARGS
from execution_engine.ffmpeg_detector import detect_ffmpeg
from execution_engine.filter_graph_builder import build_visual_filter_graph
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.render import RenderOptions

_ffmpeg_info = detect_ffmpeg()

pytestmark = pytest.mark.skipif(not _ffmpeg_info.available, reason="ffmpeg not available on this machine")


def _segment(scene_id, shot_id, start, end, *, transition_in="cut", transition_out="cut"):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path="",  # filled in per-test with a real tmp file
        asset_type="image", start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def _make_tiny_image(path):
    subprocess.run(
        [_ffmpeg_info.path, "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
         "-frames:v", "1", str(path), "-loglevel", "error"],
        check=True, timeout=30,
    )


def test_concat_chain_adjacent_to_crossfade_actually_renders_in_real_ffmpeg(tmp_path):
    # Exactly the shape that broke: scene 1 has two cut-joined shots (forces
    # a concat chain), then a crossfade into scene 2 - the concat chain's
    # output is xfade's first input, which is where the timebase mismatch
    # surfaced.
    images = [tmp_path / f"img{i}.jpg" for i in range(3)]
    for img in images:
        _make_tiny_image(img)

    plan = EditingPlan(
        editing_plan_id="ep-regression",
        segments=[
            EditingSegment(
                scene_id=1, shot_id=1, asset_path=str(images[0]), asset_type="image",
                start_time=0.0, end_time=1.0, music_cue_scene_id=1,
                transition_in="cut", transition_out="cut",
            ),
            EditingSegment(
                scene_id=1, shot_id=2, asset_path=str(images[1]), asset_type="image",
                start_time=1.0, end_time=2.0, music_cue_scene_id=1,
                transition_in="cut", transition_out="crossfade",
            ),
            EditingSegment(
                scene_id=2, shot_id=1, asset_path=str(images[2]), asset_type="image",
                start_time=2.0, end_time=3.0, music_cue_scene_id=2,
                transition_in="crossfade", transition_out="cut",
            ),
        ],
    )
    options = RenderOptions(resolution="320x240", fps=24)
    graph = build_visual_filter_graph(plan, options)

    assert "concat=n=2" in graph.filter_complex
    assert "xfade" in graph.filter_complex

    output_path = tmp_path / "output.mp4"
    argv = [_ffmpeg_info.path, *GLOBAL_ARGS]
    for img, seg in zip(images, plan.segments):
        duration = seg.end_time - seg.start_time
        argv.extend(["-loop", "1", "-t", str(duration), "-i", str(img)])
    argv.extend([
        "-filter_complex", graph.filter_complex,
        "-map", f"[{graph.video_output_label}]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p", "-r", "24",
        str(output_path),
    ])

    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, f"ffmpeg failed: {result.stderr}"
    assert output_path.is_file()
    assert output_path.stat().st_size > 0

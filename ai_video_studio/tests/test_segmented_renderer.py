import pytest

from execution_engine.errors import RenderInputError
from execution_engine.segmented_renderer import (
    SEGMENT_CHAIN_THRESHOLD,
    build_segmented_render_plan,
    execute_segmented,
    should_segment,
)
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment, compute_final_duration_seconds
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderOptions, RenderRequest, RenderResult
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline


def _segment(scene_id, shot_id, start, end, *, transition_in, transition_out, asset_type="image"):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=f"/media/s{scene_id}_{shot_id}.jpg",
        asset_type=asset_type, start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def _many_scene_segments(num_scenes: int, shot_duration: float = 5.0):
    """One shot per scene, cut-free (every scene is its own 1-shot chain),
    crossfading at every scene boundary - the exact pattern this project's
    real Editing Planner produces between scenes."""
    segments = []
    t = 0.0
    for scene_id in range(1, num_scenes + 1):
        is_first = scene_id == 1
        is_last = scene_id == num_scenes
        segments.append(_segment(
            scene_id, scene_id, t, t + shot_duration,
            transition_in="fade_from_black" if is_first else "crossfade",
            transition_out="fade_to_black" if is_last else "crossfade",
        ))
        t += shot_duration
    return segments


def _request(segments, *, output_dir="/out", options=None, narration="/media/audio/voice_script.wav"):
    editing_plan = EditingPlan(
        editing_plan_id="ep1", source_timeline_id="tl1", source_subtitle_plan_id="sp1", source_music_plan_id="mp1",
        segments=segments, total_duration_seconds=compute_final_duration_seconds(segments),
    )
    manifest = ValidatedAssetManifest(
        manifest_id="m1", source_prompt_set_id="ps", is_valid=True, narration_audio_path=narration,
    )
    return RenderRequest(
        editing_plan=editing_plan, asset_manifest=manifest,
        timeline=Timeline(timeline_id="tl1", source_asset_manifest_id="m1"),
        subtitle_plan=SubtitlePlan(subtitle_plan_id="sp1", source_timeline_id="tl1"),
        music_plan=MusicPlan(music_plan_id="mp1", source_timeline_id="tl1"),
        output_dir=output_dir, options=options or RenderOptions(),
    )


# ---- should_segment ----

def test_should_segment_false_for_few_chains():
    segments = _many_scene_segments(SEGMENT_CHAIN_THRESHOLD)
    plan = EditingPlan(segments=segments)
    assert should_segment(plan) is False


def test_should_segment_true_beyond_threshold():
    segments = _many_scene_segments(SEGMENT_CHAIN_THRESHOLD + 1)
    plan = EditingPlan(segments=segments)
    assert should_segment(plan) is True


# ---- build_segmented_render_plan: step shape ----

def test_step_count_is_chains_plus_merges_plus_final_mux(tmp_path):
    num_scenes = 6
    request = _request(_many_scene_segments(num_scenes))

    steps = build_segmented_render_plan(request, tmp_path)

    # 6 chains + 5 pairwise merges + 1 final audio mux
    assert len(steps) == num_scenes + (num_scenes - 1) + 1


def test_chain_and_merge_steps_are_video_only_final_step_has_audio(tmp_path):
    request = _request(_many_scene_segments(6))

    steps = build_segmented_render_plan(request, tmp_path)

    *intermediate_steps, final_step = steps
    for step in intermediate_steps:
        assert "-an" in step.command_spec.output_args

    assert "-an" not in final_step.command_spec.output_args
    assert final_step.command_spec.output_args[:4] == ["-map", "0:v", "-map", "1:a"]


def test_final_step_uses_narration_audio_and_real_output_path(tmp_path):
    request = _request(_many_scene_segments(6), output_dir=str(tmp_path / "renders"))

    steps = build_segmented_render_plan(request, tmp_path / "renders" / ".segments")

    final_step = steps[-1]
    assert final_step.command_spec.inputs[1].path == "/media/audio/voice_script.wav"
    assert final_step.command_spec.output_path == str(tmp_path / "renders" / "video.mp4")


def test_chain_steps_have_at_most_the_chain_size_worth_of_inputs(tmp_path):
    """The whole point: no single ffmpeg invocation in the plan ever holds
    open more inputs than one chain's own shot count - never the full
    edit's shot count."""
    request = _request(_many_scene_segments(9))  # 9 one-shot chains

    steps = build_segmented_render_plan(request, tmp_path)

    chain_steps = steps[:9]
    for step in chain_steps:
        assert len(step.command_spec.inputs) == 1  # one shot per chain in this fixture

    merge_steps = steps[9:-1]
    for step in merge_steps:
        assert len(step.command_spec.inputs) == 2  # always exactly two, regardless of position


def test_opening_and_closing_fades_land_only_on_the_true_first_and_last_chain(tmp_path):
    request = _request(_many_scene_segments(6))

    steps = build_segmented_render_plan(request, tmp_path)

    chain_steps = steps[:6]
    assert "fade=t=in" in chain_steps[0].command_spec.filter_complex
    assert "fade=t=out" not in chain_steps[0].command_spec.filter_complex
    assert "fade=t=out" in chain_steps[-1].command_spec.filter_complex
    assert "fade=t=in" not in chain_steps[-1].command_spec.filter_complex
    for step in chain_steps[1:-1]:
        assert "fade=t=in" not in step.command_spec.filter_complex
        assert "fade=t=out" not in step.command_spec.filter_complex


def test_merge_offsets_replicate_the_single_pass_accumulation_math(tmp_path):
    """The segmented pipeline must land on the exact same final duration the
    single-pass filter_graph_builder (and compute_final_duration_seconds,
    the two-independently-implemented cross-check
    test_editing_plan_duration_matches_render.py already relies on) would
    produce for the same plan - only *how* it gets there (many small ffmpeg
    processes vs one) may differ."""
    segments = _many_scene_segments(5, shot_duration=6.0)
    request = _request(segments)
    expected_total = compute_final_duration_seconds(segments)

    steps = build_segmented_render_plan(request, tmp_path)
    merge_steps = [s for s in steps if "merge" in s.description]

    # Replay the same accumulation the plan builder used, reading each
    # merge step's own offset/duration back out of its filter_complex string.
    accumulated = 6.0  # first chain's duration
    for step in merge_steps:
        fc = step.command_spec.filter_complex
        duration = float(fc.split("duration=")[1].split(":")[0])
        offset = float(fc.split("offset=")[1].split("[")[0])
        assert offset == pytest.approx(accumulated - duration, abs=1e-6)
        accumulated = accumulated + 6.0 - duration

    assert accumulated == pytest.approx(expected_total, abs=1e-6)


def test_raises_on_empty_editing_plan(tmp_path):
    request = _request([])
    with pytest.raises(RenderInputError):
        build_segmented_render_plan(request, tmp_path)


def test_raises_on_mismatched_boundary_transition(tmp_path):
    segments = _many_scene_segments(6)
    # First shot's opening transition must be fade_from_black or cut.
    segments[0].transition_in = "crossfade"
    request = _request(segments)
    with pytest.raises(RenderInputError):
        build_segmented_render_plan(request, tmp_path)


# ---- execute_segmented: orchestration ----

class _FakeExecutor:
    """Stands in for ffmpeg_executor.execute() the same way
    tests/integration/test_render_pipeline.py's module-level fakes do -
    writes a real small file at the spec's output path so cleanup/existence
    assertions exercise real filesystem behavior, not mocks."""

    def __init__(self, fail_on_call: int = None):
        self.fail_on_call = fail_on_call
        self.calls = 0

    def __call__(self, command_spec, *, ffmpeg_path, timeout_seconds):
        self.calls += 1
        if self.fail_on_call == self.calls:
            return RenderResult(
                success=False, dry_run=False, exit_code=1, error="fake ffmpeg failure",
                error_type="ffmpeg_failed", duration_seconds=0.5,
            )
        from pathlib import Path
        output = Path(command_spec.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake video bytes")
        return RenderResult(success=True, dry_run=False, output_path=str(output), exit_code=0, duration_seconds=1.5)


def test_execute_segmented_runs_every_step_and_produces_final_output(tmp_path):
    request = _request(_many_scene_segments(6), output_dir=str(tmp_path))
    fake = _FakeExecutor()

    result = execute_segmented(request, executor=fake)

    assert result.success is True
    assert result.output_path == str(tmp_path / "video.mp4")
    assert (tmp_path / "video.mp4").exists()
    # 6 chains + 5 merges + 1 final mux = 12 steps, each contributing 1.5s
    assert fake.calls == 12
    assert result.duration_seconds == pytest.approx(12 * 1.5, abs=1e-6)


def test_execute_segmented_cleans_up_intermediate_files_on_success(tmp_path):
    request = _request(_many_scene_segments(6), output_dir=str(tmp_path))
    fake = _FakeExecutor()

    execute_segmented(request, executor=fake)

    assert not (tmp_path / ".segments").exists()


def test_merge_steps_mark_both_consumed_inputs_for_cleanup(tmp_path):
    """Regression test for the real disk-space bug found in production: a
    9-chain render succeeded at every step (memory bounded, as intended)
    but the FINAL step still failed with 'No space left on device', because
    nothing deleted a merge step's two consumed inputs once it succeeded -
    every merge's growing output sat on disk simultaneously instead of only
    the newest one surviving. Each merge step must name exactly its own two
    inputs (the previous accumulated file and the chain file it just
    absorbed) as safe to delete."""
    request = _request(_many_scene_segments(6), output_dir=str(tmp_path))

    steps = build_segmented_render_plan(request, tmp_path / ".segments")

    # 6 chains + 5 merges + 1 final mux = 12 steps
    chain_steps, merge_steps, final_step = steps[:6], steps[6:11], steps[11]
    for step in chain_steps:
        assert step.cleanup_after == []

    for i, step in enumerate(merge_steps):
        assert len(step.cleanup_after) == 2
        # the second consumed input is always the (i+1)-th chain's own output
        assert step.cleanup_after[1] == tmp_path / ".segments" / f"chain_{i + 1}.mp4"

    # the final mux step's cleanup_after names the last merge's own output -
    # the one video-only file it consumed and baked into the real result.
    assert final_step.cleanup_after == [tmp_path / ".segments" / "merge_5.mp4"]


def test_execute_segmented_never_keeps_more_than_a_bounded_number_of_intermediates_on_disk(tmp_path):
    """The actual regression, exercised end-to-end. Chains are still all
    built before any merge starts (each chain is a small, constant-size
    clip, so that phase's own peak of `num_scenes` files is cheap and
    expected) - what must NOT happen is the merge phase adding further,
    ever-larger accumulation on top of that: each merge step nets -1 file
    (consumes 2, produces 1), so the file count must trend strictly
    downward once merging starts, never re-growing past the chain-building
    phase's own peak. Before the per-step cleanup fix, nothing was deleted
    until the very end, so the count instead grew monotonically to
    num_scenes (chains) + (num_scenes - 1) (merges) = 17 files - each
    later merge file also a full re-encode of more of the timeline, which
    is what exhausted real disk space in production."""
    num_scenes = 9
    request = _request(_many_scene_segments(num_scenes), output_dir=str(tmp_path))
    segment_dir = tmp_path / ".segments"
    file_counts = []

    class _TrackingExecutor(_FakeExecutor):
        def __call__(self, command_spec, *, ffmpeg_path, timeout_seconds):
            result = super().__call__(command_spec, ffmpeg_path=ffmpeg_path, timeout_seconds=timeout_seconds)
            if segment_dir.exists():
                file_counts.append(len(list(segment_dir.glob("*.mp4"))))
            return result

    result = execute_segmented(request, executor=_TrackingExecutor())

    assert result.success is True
    chain_phase_peak = max(file_counts[:num_scenes])
    assert chain_phase_peak == num_scenes  # all chains built before merging starts - expected, cheap

    # Before the fix, this would have kept climbing (17 by the final step).
    # With per-step cleanup, nothing after the chain-building phase may
    # exceed that phase's own peak by more than the one transient file a
    # create-then-delete step ordering briefly produces (the new merge
    # output is written before its two now-stale inputs are deleted, so a
    # crash mid-step never leaves zero valid copies of that data).
    merge_and_final_phase = file_counts[num_scenes:]
    assert max(merge_and_final_phase) <= chain_phase_peak + 1, file_counts
    # And it must actually trend down, not hover near the peak throughout -
    # the real signature of "each merge nets -1", not "still accumulating".
    assert file_counts[-1] <= 2, file_counts


def test_execute_segmented_stops_at_first_failing_step(tmp_path):
    request = _request(_many_scene_segments(6), output_dir=str(tmp_path))
    fake = _FakeExecutor(fail_on_call=3)

    result = execute_segmented(request, executor=fake)

    assert result.success is False
    assert result.error == "fake ffmpeg failure"
    assert fake.calls == 3  # never ran the remaining 9 steps
    assert not (tmp_path / "video.mp4").exists()
    assert not (tmp_path / ".segments").exists()  # still cleaned up on failure

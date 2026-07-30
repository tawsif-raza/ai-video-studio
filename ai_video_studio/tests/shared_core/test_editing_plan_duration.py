"""Regression coverage for compute_final_duration_seconds (Release-Prep
milestone). D4 cloud validation found that EditingPlan.total_duration_seconds
was set to the Timeline's raw, contiguous sum of shot durations, while the
render's own filter graph applies real crossfades at scene boundaries that
overlap (and so shrink) the actual rendered runtime below that sum -
postflight then compared the two and failed by design for any multi-scene
project. These tests pin the corrected arithmetic directly, independent of
build_editing_plan or any rendering; test_editing_planner.py covers the
integration with build_editing_plan, and
tests/integration/test_editing_plan_duration_matches_render.py cross-checks
this same arithmetic against a real ffmpeg render's probed duration."""

from shared_core.contracts.editing_plan import EditingSegment, compute_final_duration_seconds


def _segment(scene_id, shot_id, start, end, *, transition_in="cut", transition_out="cut"):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path="", asset_type="image",
        start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def test_no_segments_yields_zero():
    assert compute_final_duration_seconds([]) == 0.0


def test_single_segment_matches_its_own_duration():
    segments = [_segment(1, 1, 0.0, 8.0, transition_in="fade_from_black", transition_out="fade_to_black")]
    assert compute_final_duration_seconds(segments) == 8.0


def test_cut_only_chain_matches_raw_sum():
    # No crossfades anywhere - hard cuts and edge fades never overlap runtime,
    # so the final duration must equal the segments' own contiguous sum.
    segments = [
        _segment(1, 1, 0.0, 5.0, transition_in="fade_from_black", transition_out="cut"),
        _segment(1, 2, 5.0, 8.0, transition_in="cut", transition_out="cut"),
        _segment(1, 3, 8.0, 10.0, transition_in="cut", transition_out="fade_to_black"),
    ]
    assert compute_final_duration_seconds(segments) == 10.0


def test_single_crossfade_boundary_shrinks_total_by_the_overlap():
    # Two 10s chains joined by one crossfade: the overlap (capped at 0.75s,
    # well under half of either 10s side) is subtracted exactly once.
    segments = [
        _segment(1, 1, 0.0, 10.0, transition_in="fade_from_black", transition_out="crossfade"),
        _segment(2, 1, 10.0, 20.0, transition_in="crossfade", transition_out="fade_to_black"),
    ]
    assert compute_final_duration_seconds(segments) == 19.25


def test_multi_scene_crossfade_matches_known_real_render():
    # The exact shape D4 cloud validation hit: scene1 (5s) -x-> scene2 (3 cut
    # shots, 5+3+2=10s) -x-> scene3 (5s). Real ffmpeg render of this precise
    # plan (tests/integration/test_editing_plan_duration_matches_render.py)
    # measured 18.458333s; two 0.75s crossfade overlaps against a raw sum of
    # 20s gives exactly this figure by construction.
    segments = [
        _segment(1, 1, 0.0, 5.0, transition_in="fade_from_black", transition_out="crossfade"),
        _segment(2, 1, 5.0, 10.0, transition_in="crossfade", transition_out="cut"),
        _segment(2, 2, 10.0, 13.0, transition_in="cut", transition_out="cut"),
        _segment(2, 3, 13.0, 15.0, transition_in="cut", transition_out="crossfade"),
        _segment(3, 1, 15.0, 20.0, transition_in="crossfade", transition_out="fade_to_black"),
    ]
    assert compute_final_duration_seconds(segments) == 18.5


def test_crossfade_overlap_capped_for_very_short_clips():
    # Two 1s chains either side of a crossfade: the 0.75s default overlap
    # would exceed half of either clip (0.5s), so it must be capped to 0.5s,
    # not silently produce a negative or zero-length result.
    segments = [
        _segment(1, 1, 0.0, 1.0, transition_in="fade_from_black", transition_out="crossfade"),
        _segment(2, 1, 1.0, 2.0, transition_in="crossfade", transition_out="fade_to_black"),
    ]
    assert compute_final_duration_seconds(segments) == 1.5

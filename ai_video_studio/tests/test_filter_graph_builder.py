import pytest

from execution_engine.errors import RenderInputError
from execution_engine.filter_graph_builder import (
    CROSSFADE_SECONDS,
    EDGE_FADE_SECONDS,
    MUSIC_BASE_LEVEL,
    MUSIC_DUCK_FACTOR,
    build_audio_filter_graph,
    build_visual_filter_graph,
)
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.music_plan import DuckWindow, MusicCue, MusicPlan
from shared_core.contracts.render import RenderOptions


def _segment(scene_id, shot_id, start, end, *, asset_type="image", transition_in="cut", transition_out="cut"):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=f"/i/s{scene_id}s{shot_id}.{asset_type}",
        asset_type=asset_type, start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in=transition_in, transition_out=transition_out,
    )


def _plan(*segments):
    return EditingPlan(editing_plan_id="ep1", segments=list(segments))


def _default_options():
    return RenderOptions()


# ---- single segment ----

def test_single_segment_no_boundary_fades_yields_plain_normalize():
    plan = _plan(_segment(1, 1, 0.0, 5.0))
    graph = build_visual_filter_graph(plan, _default_options())

    assert "fade=" not in graph.filter_complex
    assert "xfade" not in graph.filter_complex
    assert "concat" not in graph.filter_complex
    assert "scale=1920:1080" in graph.filter_complex
    assert "fps=30" in graph.filter_complex
    assert graph.video_output_label == "n0"


def test_single_segment_with_fade_from_and_to_black_chains_both():
    plan = _plan(_segment(1, 1, 0.0, 5.0, transition_in="fade_from_black", transition_out="fade_to_black"))
    graph = build_visual_filter_graph(plan, _default_options())

    assert graph.filter_complex.count("fade=t=in") == 1
    assert graph.filter_complex.count("fade=t=out") == 1
    # fade-in chains from the normalized label, fade-out chains from the fade-in's output
    assert "[n0]fade=t=in:st=0" in graph.filter_complex
    assert "fade=t=out:st=" in graph.filter_complex
    assert graph.video_output_label.startswith("fo")


# ---- normalization ----

def test_resolution_and_fps_applied_to_every_visual_input():
    plan = _plan(_segment(1, 1, 0.0, 2.0), _segment(1, 2, 2.0, 4.0))
    graph = build_visual_filter_graph(plan, RenderOptions(resolution="1280x720", fps=24))

    assert graph.filter_complex.count("scale=1280:720") == 2
    # 2 per-input normalizations + 1 re-assertion after the concat that joins
    # them (concat resets timebase - see build_visual_filter_graph) - without
    # the re-assertion this graph would fail in real ffmpeg with a timebase
    # mismatch the moment this chain sits next to a crossfade.
    assert graph.filter_complex.count("fps=24") == 3
    assert graph.filter_complex.count("setsar=1") == 2


def test_invalid_resolution_format_rejected():
    plan = _plan(_segment(1, 1, 0.0, 2.0))
    with pytest.raises(RenderInputError, match="Invalid resolution"):
        build_visual_filter_graph(plan, RenderOptions(resolution="not-a-resolution"))


def test_zero_or_negative_resolution_rejected():
    plan = _plan(_segment(1, 1, 0.0, 2.0))
    with pytest.raises(RenderInputError, match="positive"):
        build_visual_filter_graph(plan, RenderOptions(resolution="0x1080"))


def test_nonpositive_fps_rejected():
    plan = _plan(_segment(1, 1, 0.0, 2.0))
    with pytest.raises(RenderInputError, match="fps"):
        build_visual_filter_graph(plan, RenderOptions(fps=0))


def test_video_segment_is_trimmed_image_segment_is_not():
    plan = _plan(_segment(1, 1, 0.0, 3.0, asset_type="video"), _segment(1, 2, 3.0, 6.0, asset_type="image"))
    graph = build_visual_filter_graph(plan, _default_options())

    assert "trim=duration=3" in graph.filter_complex
    # only the video segment (input 0) is trimmed - exactly one trim= in the whole graph
    assert graph.filter_complex.count("trim=duration") == 1


# ---- cuts within a scene (concat) ----

def test_same_scene_cut_joins_use_concat():
    plan = _plan(_segment(1, 1, 0.0, 2.0), _segment(1, 2, 2.0, 5.0), _segment(1, 3, 5.0, 7.0))
    graph = build_visual_filter_graph(plan, _default_options())

    assert "concat=n=3:v=1:a=0" in graph.filter_complex
    assert "xfade" not in graph.filter_complex
    assert graph.video_output_label == "chain0"


# ---- crossfades at scene boundaries ----

def test_scene_boundary_crossfade_uses_xfade_with_computed_offset():
    plan = _plan(
        _segment(1, 1, 0.0, 10.0, transition_out="crossfade"),
        _segment(2, 1, 10.0, 20.0, transition_in="crossfade"),
    )
    graph = build_visual_filter_graph(plan, _default_options())

    assert "xfade=transition=fade" in graph.filter_complex
    # full crossfade duration fits (10s clips, cap is CROSSFADE_SECONDS)
    assert f"duration={CROSSFADE_SECONDS:g}" in graph.filter_complex
    assert f"offset={10 - CROSSFADE_SECONDS:g}" in graph.filter_complex


def test_crossfade_duration_capped_to_half_shorter_clip():
    plan = _plan(
        _segment(1, 1, 0.0, 1.0, transition_out="crossfade"),  # 1s clip - forces a cap
        _segment(2, 1, 1.0, 11.0, transition_in="crossfade"),
    )
    graph = build_visual_filter_graph(plan, _default_options())

    assert "duration=0.5" in graph.filter_complex  # capped to 1.0/2
    assert "offset=0.5" in graph.filter_complex  # 1.0 - 0.5


def test_multiple_scenes_produce_multiple_chains_and_sequential_xfades():
    plan = _plan(
        _segment(1, 1, 0.0, 2.0, transition_out="crossfade"),
        _segment(2, 1, 2.0, 4.0, transition_in="crossfade", transition_out="crossfade"),
        _segment(3, 1, 4.0, 6.0, transition_in="crossfade"),
    )
    graph = build_visual_filter_graph(plan, _default_options())

    assert graph.filter_complex.count("xfade=transition=fade") == 2
    assert graph.video_output_label == "xf2"


def test_mixed_cut_and_crossfade_within_multi_shot_scenes():
    plan = _plan(
        _segment(1, 1, 0.0, 2.0),                                    # scene 1, shot 1 (cut in/out)
        _segment(1, 2, 2.0, 4.0, transition_out="crossfade"),        # scene 1, shot 2 -> crossfade to scene 2
        _segment(2, 1, 4.0, 6.0, transition_in="crossfade"),         # scene 2, shot 1
        _segment(2, 2, 6.0, 8.0),                                    # scene 2, shot 2 (cut in/out)
    )
    graph = build_visual_filter_graph(plan, _default_options())

    assert graph.filter_complex.count("concat=n=2:v=1:a=0") == 2  # one chain per scene
    assert graph.filter_complex.count("xfade=transition=fade") == 1  # one scene boundary


# ---- boundary / consistency validation ----

def test_empty_segments_rejected():
    with pytest.raises(RenderInputError, match="no segments"):
        build_visual_filter_graph(_plan(), _default_options())


def test_first_segment_opening_transition_must_be_fade_from_black_or_cut():
    plan = _plan(_segment(1, 1, 0.0, 2.0, transition_in="crossfade"), _segment(1, 2, 2.0, 4.0))
    with pytest.raises(RenderInputError, match="opening transition"):
        build_visual_filter_graph(plan, _default_options())


def test_last_segment_closing_transition_must_be_fade_to_black_or_cut():
    plan = _plan(_segment(1, 1, 0.0, 2.0), _segment(1, 2, 2.0, 4.0, transition_out="crossfade"))
    with pytest.raises(RenderInputError, match="closing transition"):
        build_visual_filter_graph(plan, _default_options())


def test_inconsistent_adjacent_transitions_rejected():
    plan = _plan(
        _segment(1, 1, 0.0, 2.0, transition_out="crossfade"),
        _segment(1, 2, 2.0, 4.0, transition_in="cut"),  # doesn't match prev's transition_out
    )
    with pytest.raises(RenderInputError, match="Transition mismatch"):
        build_visual_filter_graph(plan, _default_options())


def test_unsupported_transition_value_rejected():
    plan = _plan(
        _segment(1, 1, 0.0, 2.0, transition_out="wipe"),
        _segment(1, 2, 2.0, 4.0, transition_in="wipe"),
    )
    with pytest.raises(RenderInputError, match="Unsupported inter-shot transition"):
        build_visual_filter_graph(plan, _default_options())


def test_zero_length_segment_rejected():
    plan = _plan(_segment(1, 1, 5.0, 5.0))
    with pytest.raises(RenderInputError, match="non-positive duration"):
        build_visual_filter_graph(plan, _default_options())


# ---- determinism ----

def test_same_input_produces_identical_graph():
    plan = _plan(
        _segment(1, 1, 0.0, 2.0, transition_out="crossfade"),
        _segment(2, 1, 2.0, 5.0, transition_in="crossfade"),
    )
    options = RenderOptions()
    first = build_visual_filter_graph(plan, options)
    second = build_visual_filter_graph(plan, options)
    assert first == second


def test_edge_fade_constant_used_when_uncapped():
    plan = _plan(_segment(1, 1, 0.0, 10.0, transition_in="fade_from_black"))
    graph = build_visual_filter_graph(plan, _default_options())
    assert f"d={EDGE_FADE_SECONDS:g}" in graph.filter_complex


# ---- audio mixing (build_audio_filter_graph) ----

def _music_cue(scene_id, start, end, *, is_silent=False, fade_in=0.0, fade_out=0.0, duck_windows=None):
    return MusicCue(
        scene_id=scene_id, start_time=start, end_time=end, mood="calm", tempo="slow", intensity="low",
        is_silent=is_silent, fade_in_seconds=fade_in, fade_out_seconds=fade_out,
        duck_windows=duck_windows or [],
    )


def _music_plan(*cues):
    return MusicPlan(music_plan_id="mp1", source_timeline_id="tl1", cues=list(cues))


def test_narration_mapped_unfiltered_and_stays_primary_via_normalize_zero():
    plan = _music_plan(_music_cue(1, 0.0, 5.0))
    graph = build_audio_filter_graph(plan, narration_input_index=2, music_input_index=3)

    assert "[2:a]" in graph.filter_complex  # narration referenced raw, never filtered
    assert "amix=inputs=2" in graph.filter_complex
    assert "normalize=0" in graph.filter_complex
    assert graph.audio_output_label == "aout"


def test_music_scaled_to_base_level():
    plan = _music_plan(_music_cue(1, 0.0, 5.0))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert f"[2:a]volume={MUSIC_BASE_LEVEL:g}[mbase]" in graph.filter_complex


def test_silent_cue_mutes_music_for_its_whole_span():
    plan = _music_plan(_music_cue(1, 0.0, 5.0, is_silent=True))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "volume=0:enable='between(t,0,5)'" in graph.filter_complex


def test_duck_window_reduces_by_duck_factor_not_absolute_level():
    plan = _music_plan(_music_cue(1, 0.0, 10.0, duck_windows=[DuckWindow(start_time=2.0, end_time=4.0)]))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert f"volume={MUSIC_DUCK_FACTOR:g}:enable='between(t,2,4)'" in graph.filter_complex


def test_multiple_duck_windows_all_present_and_sorted():
    plan = _music_plan(_music_cue(
        1, 0.0, 20.0,
        duck_windows=[DuckWindow(start_time=10.0, end_time=12.0), DuckWindow(start_time=1.0, end_time=3.0)],
    ))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    first_idx = graph.filter_complex.index("between(t,1,3)")
    second_idx = graph.filter_complex.index("between(t,10,12)")
    assert first_idx < second_idx  # sorted by start_time regardless of input order


def test_fade_in_uses_first_non_silent_cues_own_values():
    plan = _music_plan(_music_cue(1, 0.0, 5.0, fade_in=1.5))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "afade=t=in:st=0:d=1.5[mfadein]" in graph.filter_complex


def test_fade_in_anchored_to_first_non_silent_cues_start_time_when_earlier_cue_is_silent():
    plan = _music_plan(
        _music_cue(1, 0.0, 3.0, is_silent=True),
        _music_cue(2, 3.0, 10.0, fade_in=1.0),
    )
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "afade=t=in:st=3:d=1[mfadein]" in graph.filter_complex


def test_fade_out_uses_last_non_silent_cues_own_values():
    plan = _music_plan(_music_cue(1, 0.0, 10.0, fade_out=2.0))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "afade=t=out:st=8:d=2[mfadeout]" in graph.filter_complex


def test_interior_cue_fades_not_applied_only_outermost():
    # three non-silent cues: only the first cue's fade_in and the last cue's
    # fade_out should produce an afade - the middle cue's own fade values
    # (meant for a future per-scene-track milestone) must not dip the one
    # continuous track mid-video.
    plan = _music_plan(
        _music_cue(1, 0.0, 5.0, fade_in=1.5, fade_out=1.0),
        _music_cue(2, 5.0, 10.0, fade_in=1.0, fade_out=1.0),
        _music_cue(3, 10.0, 15.0, fade_in=1.0, fade_out=1.5),
    )
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert graph.filter_complex.count("afade=t=in") == 1
    assert graph.filter_complex.count("afade=t=out") == 1
    assert "afade=t=in:st=0:d=1.5" in graph.filter_complex
    assert "afade=t=out:st=13.5:d=1.5" in graph.filter_complex


def test_zero_fade_values_produce_no_afade():
    plan = _music_plan(_music_cue(1, 0.0, 5.0, fade_in=0.0, fade_out=0.0))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "afade" not in graph.filter_complex


def test_no_cues_still_produces_a_valid_mix_graph():
    plan = _music_plan()
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "amix=inputs=2" in graph.filter_complex
    assert "afade" not in graph.filter_complex


def test_all_silent_cues_music_muted_throughout_but_graph_still_valid():
    plan = _music_plan(_music_cue(1, 0.0, 5.0, is_silent=True))
    graph = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert "volume=0:enable='between(t,0,5)'" in graph.filter_complex
    assert "afade" not in graph.filter_complex  # no non-silent cue to anchor a fade to


def test_same_input_produces_identical_audio_graph():
    plan = _music_plan(_music_cue(1, 0.0, 5.0, fade_in=1.0, fade_out=1.0))
    first = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    second = build_audio_filter_graph(plan, narration_input_index=1, music_input_index=2)
    assert first == second

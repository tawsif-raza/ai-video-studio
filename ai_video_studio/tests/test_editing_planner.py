import pytest

from agents.base.exceptions import ContractViolationError
from agents.editing_planner.contract import EditingPlannerInput
from agents.editing_planner.validator import build_editing_plan
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.music_plan import MusicCue
from shared_core.contracts.music_plan import MusicPlan as MusicPlanModel
from shared_core.contracts.subtitle import SubtitleCue, SubtitlePlan
from shared_core.contracts.timeline import Timeline, TimelineClip


def _manifest(manifest_id="manifest-1"):
    return ValidatedAssetManifest(manifest_id=manifest_id, source_prompt_set_id="abc", is_valid=True)


def _clip(scene_id, shot_id, start, end, asset_type="image"):
    return TimelineClip(
        scene_id=scene_id, shot_id=shot_id, asset_path=f"/i/s{scene_id}s{shot_id}.{asset_type}",
        asset_type=asset_type, duration_seconds=end - start, start_time=start, end_time=end,
    )


def _timeline(*clips, timeline_id="tl-1", manifest_id="manifest-1"):
    total = max((c.end_time for c in clips), default=0.0)
    return Timeline(
        timeline_id=timeline_id, source_asset_manifest_id=manifest_id,
        clips=list(clips), total_duration_seconds=total,
    )


def _subtitle_plan(*cues, timeline_id="tl-1"):
    return SubtitlePlan(source_timeline_id=timeline_id, cues=list(cues))


def _music_plan(*cues, timeline_id="tl-1"):
    return MusicPlanModel(source_timeline_id=timeline_id, cues=list(cues))


def _music_cue(scene_id, start, end):
    return MusicCue(scene_id=scene_id, start_time=start, end_time=end, mood="neutral", tempo="medium", intensity="medium")


def test_segments_reference_resolved_clip_assets():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0, "video"))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline,
        subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 5.0)),
    ))

    assert len(plan.segments) == 1
    seg = plan.segments[0]
    assert seg.scene_id == 1
    assert seg.shot_id == 1
    assert seg.asset_path == "/i/s1s1.video"
    assert seg.asset_type == "video"
    assert seg.start_time == 0.0
    assert seg.end_time == 5.0
    assert seg.music_cue_scene_id == 1


def test_single_scene_first_and_last_shot_get_edge_transitions():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), _clip(1, 2, 5.0, 10.0))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline,
        subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 10.0)),
    ))

    assert plan.segments[0].transition_in == "fade_from_black"
    assert plan.segments[0].transition_out == "cut"  # same scene, next shot
    assert plan.segments[1].transition_in == "cut"
    assert plan.segments[1].transition_out == "fade_to_black"


def test_scene_boundary_gets_crossfade():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), _clip(2, 1, 5.0, 10.0))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline, subtitle_plan=_subtitle_plan(),
        music_plan=_music_plan(_music_cue(1, 0.0, 5.0), _music_cue(2, 5.0, 10.0)),
    ))

    assert plan.segments[0].transition_out == "crossfade"
    assert plan.segments[1].transition_in == "crossfade"


def test_total_duration_reflects_crossfade_shrinkage_not_raw_timeline_sum():
    # Regression for the Release-Prep rendering-reliability defect: the
    # Timeline's raw sum here is 10.0s, but the two 5s clips are joined by a
    # crossfade at the scene boundary, which overlaps (and so shrinks) the
    # actual rendered runtime. total_duration_seconds must reflect that
    # shrinkage, not the Timeline's untouched sum - postflight validation
    # compares the rendered file's real duration against this exact field.
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), _clip(2, 1, 5.0, 10.0))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline, subtitle_plan=_subtitle_plan(),
        music_plan=_music_plan(_music_cue(1, 0.0, 5.0), _music_cue(2, 5.0, 10.0)),
    ))

    assert timeline.total_duration_seconds == 10.0
    assert plan.total_duration_seconds == 9.25  # 10.0 - 0.75s crossfade overlap
    assert plan.total_duration_seconds < timeline.total_duration_seconds


def test_image_gets_ken_burns_placeholder_video_gets_none():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0, "image"), _clip(1, 2, 5.0, 10.0, "video"))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline,
        subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 10.0)),
    ))

    assert plan.segments[0].effects_placeholders == ["ken_burns"]
    assert plan.segments[1].effects_placeholders == []


def test_black_placeholder_clip_passes_through_with_no_ken_burns():
    # Release milestone: a shot Timeline Planning resolved to "black" (no
    # real asset - Asset Validation tolerated it as missing) carries no real
    # asset_path and gets no ken_burns placeholder, same as a video clip.
    clip = TimelineClip(
        scene_id=1, shot_id=1, asset_path=None, asset_type="black",
        duration_seconds=5, start_time=0.0, end_time=5.0,
    )
    timeline = _timeline(clip)
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline,
        subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 5.0)),
    ))

    assert plan.segments[0].asset_path is None
    assert plan.segments[0].asset_type == "black"
    assert plan.segments[0].effects_placeholders == []


def test_subtitle_cue_indices_assigned_by_time_overlap():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), _clip(1, 2, 5.0, 10.0))
    subtitle_plan = _subtitle_plan(
        SubtitleCue(sequence_index=1, scene_id=1, text="a", start_time=0.0, end_time=3.0),
        SubtitleCue(sequence_index=2, scene_id=1, text="b", start_time=3.0, end_time=7.0),  # spans both clips
        SubtitleCue(sequence_index=3, scene_id=1, text="c", start_time=7.0, end_time=10.0),
    )
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline,
        subtitle_plan=subtitle_plan, music_plan=_music_plan(_music_cue(1, 0.0, 10.0)),
    ))

    assert plan.segments[0].subtitle_cue_indices == [1, 2]
    assert plan.segments[1].subtitle_cue_indices == [2, 3]


def test_no_subtitle_cues_yields_empty_indices():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline,
        subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 5.0)),
    ))

    assert plan.segments[0].subtitle_cue_indices == []


def test_source_ids_recorded_on_plan():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0))
    subtitle_plan = _subtitle_plan()
    music_plan = _music_plan(_music_cue(1, 0.0, 5.0))
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline, subtitle_plan=subtitle_plan, music_plan=music_plan,
    ))

    assert plan.source_timeline_id == timeline.timeline_id
    assert plan.source_subtitle_plan_id == subtitle_plan.subtitle_plan_id
    assert plan.source_music_plan_id == music_plan.music_plan_id
    assert plan.total_duration_seconds == 5.0


def test_mismatched_asset_manifest_rejected():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), manifest_id="manifest-1")
    with pytest.raises(ContractViolationError):
        build_editing_plan(EditingPlannerInput(
            asset_manifest=_manifest(manifest_id="manifest-DIFFERENT"), timeline=timeline,
            subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 5.0)),
        ))


def test_mismatched_subtitle_plan_source_timeline_rejected():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), timeline_id="tl-1")
    with pytest.raises(ContractViolationError):
        build_editing_plan(EditingPlannerInput(
            asset_manifest=_manifest(), timeline=timeline,
            subtitle_plan=_subtitle_plan(timeline_id="tl-DIFFERENT"),
            music_plan=_music_plan(_music_cue(1, 0.0, 5.0), timeline_id="tl-1"),
        ))


def test_mismatched_music_plan_source_timeline_rejected():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), timeline_id="tl-1")
    with pytest.raises(ContractViolationError):
        build_editing_plan(EditingPlannerInput(
            asset_manifest=_manifest(), timeline=timeline,
            subtitle_plan=_subtitle_plan(timeline_id="tl-1"),
            music_plan=_music_plan(_music_cue(1, 0.0, 5.0), timeline_id="tl-DIFFERENT"),
        ))


def test_missing_music_cue_for_timeline_scene_rejected():
    timeline = _timeline(_clip(1, 1, 0.0, 5.0), _clip(2, 1, 5.0, 10.0))
    with pytest.raises(ContractViolationError):
        build_editing_plan(EditingPlannerInput(
            asset_manifest=_manifest(), timeline=timeline,
            subtitle_plan=_subtitle_plan(), music_plan=_music_plan(_music_cue(1, 0.0, 5.0)),  # scene 2 missing
        ))


def test_empty_timeline_yields_empty_editing_plan():
    timeline = _timeline()
    plan = build_editing_plan(EditingPlannerInput(
        asset_manifest=_manifest(), timeline=timeline, subtitle_plan=_subtitle_plan(), music_plan=_music_plan(),
    ))

    assert plan.segments == []
    assert plan.total_duration_seconds == 0.0

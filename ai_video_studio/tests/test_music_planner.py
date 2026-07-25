import pytest

from agents.base.exceptions import ContractViolationError
from agents.music_planner.contract import MusicPlannerInput, SceneMood
from agents.music_planner.validator import build_music_plan
from shared_core.contracts.subtitle import SubtitleCue, SubtitlePlan
from shared_core.contracts.timeline import Timeline, TimelineClip


def _clip(scene_id, shot_id, start, end):
    return TimelineClip(
        scene_id=scene_id, shot_id=shot_id, asset_path=f"/i/s{scene_id}s{shot_id}.png",
        asset_type="image", duration_seconds=end - start, start_time=start, end_time=end,
    )


def _timeline(*clips, timeline_id="tl-1"):
    total = max((c.end_time for c in clips), default=0.0)
    return Timeline(timeline_id=timeline_id, clips=list(clips), total_duration_seconds=total)


def _subtitle_plan(*cues):
    return SubtitlePlan(cues=list(cues))


def _moods(*entries):
    return [SceneMood(scene_id=s, mood=m) for s, m in entries]


def test_tense_mood_classified_fast_high_intensity():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0))
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "cautious and hesitant")),
    ))

    assert plan.cues[0].mood == "tense"
    assert plan.cues[0].tempo == "fast"
    assert plan.cues[0].intensity == "high"
    assert plan.cues[0].is_silent is False


def test_uplifting_mood_classified_medium_tempo():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0))
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "hopeful and determined")),
    ))

    assert plan.cues[0].mood == "uplifting"
    assert plan.cues[0].tempo == "medium"


def test_unknown_mood_falls_back_to_neutral():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0))
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "a bustling marketplace")),
    ))

    assert plan.cues[0].mood == "neutral"
    assert plan.cues[0].tempo == "medium"
    assert plan.cues[0].intensity == "medium"


def test_first_and_last_scene_get_edge_fades_interior_gets_boundary_fades():
    timeline = _timeline(
        _clip(1, 1, 0.0, 10.0), _clip(2, 1, 10.0, 20.0), _clip(3, 1, 20.0, 30.0),
    )
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(),
        scene_moods=_moods((1, "hopeful"), (2, "hopeful"), (3, "hopeful")),
    ))

    assert plan.cues[0].fade_in_seconds == 1.5  # edge
    assert plan.cues[0].fade_out_seconds == 1.0  # boundary
    assert plan.cues[1].fade_in_seconds == 1.0  # boundary
    assert plan.cues[1].fade_out_seconds == 1.0  # boundary
    assert plan.cues[2].fade_in_seconds == 1.0  # boundary
    assert plan.cues[2].fade_out_seconds == 1.5  # edge


def test_fades_never_exceed_half_scene_duration():
    timeline = _timeline(_clip(1, 1, 0.0, 2.0))  # short scene, edge fades on both sides
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "hopeful")),
    ))

    assert plan.cues[0].fade_in_seconds == 1.0
    assert plan.cues[0].fade_out_seconds == 1.0


def test_short_scene_is_planned_silent():
    timeline = _timeline(_clip(1, 1, 0.0, 1.0))  # under the 1.5s floor
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "hopeful")),
    ))

    assert plan.cues[0].is_silent is True
    assert plan.cues[0].tempo == "none"
    assert plan.cues[0].intensity == "none"
    assert plan.cues[0].duck_windows == []


def test_silence_keyword_forces_silent_regardless_of_duration():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0))
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "a tense silence falls")),
    ))

    assert plan.cues[0].is_silent is True


def test_duck_windows_populated_from_matching_scene_subtitle_cues():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0), _clip(2, 1, 10.0, 20.0))
    subtitle_plan = _subtitle_plan(
        SubtitleCue(sequence_index=1, scene_id=1, text="Line one.", start_time=0.0, end_time=3.0),
        SubtitleCue(sequence_index=2, scene_id=1, text="Line two.", start_time=3.0, end_time=6.0),
        SubtitleCue(sequence_index=3, scene_id=2, text="Line three.", start_time=10.0, end_time=15.0),
    )
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=subtitle_plan, scene_moods=_moods((1, "hopeful"), (2, "calm")),
    ))

    scene_1_cue = next(c for c in plan.cues if c.scene_id == 1)
    scene_2_cue = next(c for c in plan.cues if c.scene_id == 2)
    assert len(scene_1_cue.duck_windows) == 2
    assert scene_1_cue.duck_windows[0].start_time == 0.0
    assert scene_1_cue.duck_windows[0].end_time == 3.0
    assert scene_1_cue.duck_windows[1].start_time == 3.0
    assert len(scene_2_cue.duck_windows) == 1
    assert scene_2_cue.duck_windows[0].start_time == 10.0


def test_no_subtitle_cues_for_scene_yields_empty_duck_windows():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0))
    plan = build_music_plan(MusicPlannerInput(
        timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "hopeful")),
    ))

    assert plan.cues[0].duck_windows == []


def test_missing_mood_for_timeline_scene_rejected():
    timeline = _timeline(_clip(1, 1, 0.0, 10.0), _clip(2, 1, 10.0, 20.0))
    with pytest.raises(ContractViolationError):
        build_music_plan(MusicPlannerInput(
            timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=_moods((1, "hopeful")),
        ))


def test_empty_timeline_yields_empty_music_plan():
    timeline = _timeline()
    plan = build_music_plan(MusicPlannerInput(timeline=timeline, subtitle_plan=_subtitle_plan(), scene_moods=[]))

    assert plan.cues == []

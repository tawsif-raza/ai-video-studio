import pytest

from agents.base.exceptions import ContractViolationError
from agents.subtitle_planner.contract import SubtitlePlannerInput
from agents.subtitle_planner.validator import build_subtitle_plan
from shared_core.contracts.timeline import Timeline, VoiceSegment


def _timeline(*segments, timeline_id="tl-1"):
    voice_segments = [
        VoiceSegment(scene_id=s, start_time=start, end_time=end, audio_path="/media/audio/voice_script.wav")
        for s, start, end in segments
    ]
    return Timeline(timeline_id=timeline_id, voice_segments=voice_segments, total_duration_seconds=max(
        (end for _, _, end in segments), default=0.0
    ))


def test_single_short_sentence_becomes_one_cue_spanning_full_window():
    timeline = _timeline((1, 0.0, 10.0))
    plan = build_subtitle_plan(SubtitlePlannerInput(timeline=timeline, narration_paragraphs=["Mira stands at the edge."]))

    assert len(plan.cues) == 1
    assert plan.cues[0].scene_id == 1
    assert plan.cues[0].sequence_index == 1
    assert plan.cues[0].start_time == 0.0
    assert plan.cues[0].end_time == 10.0
    assert plan.cues[0].text == "Mira stands at the edge."


def test_multiple_sentences_split_into_multiple_cues_in_order():
    timeline = _timeline((1, 0.0, 20.0))
    text = "Mira stands at the edge. She looks determined. The forest is quiet."
    plan = build_subtitle_plan(SubtitlePlannerInput(timeline=timeline, narration_paragraphs=[text]))

    assert len(plan.cues) == 3
    assert [c.sequence_index for c in plan.cues] == [1, 2, 3]
    assert plan.cues[0].text == "Mira stands at the edge."
    assert plan.cues[1].text == "She looks determined."
    assert plan.cues[2].text == "The forest is quiet."
    assert plan.cues[0].start_time == 0.0
    assert plan.cues[-1].end_time == 20.0


def test_cues_are_contiguous_and_non_overlapping_within_a_scene():
    timeline = _timeline((1, 0.0, 20.0))
    text = "Mira stands at the edge. She looks determined. The forest is quiet."
    plan = build_subtitle_plan(SubtitlePlannerInput(timeline=timeline, narration_paragraphs=[text]))

    for prev, nxt in zip(plan.cues, plan.cues[1:]):
        assert prev.end_time == nxt.start_time


def test_long_sentence_is_word_wrapped_under_max_chars():
    timeline = _timeline((1, 0.0, 10.0))
    long_sentence = "Mira " * 40 + "stands."  # forces word-wrapping
    plan = build_subtitle_plan(SubtitlePlannerInput(timeline=timeline, narration_paragraphs=[long_sentence.strip()]))

    assert len(plan.cues) > 1
    for cue in plan.cues:
        assert len(cue.text) <= 84


def test_sequence_index_continues_across_scenes():
    timeline = _timeline((1, 0.0, 10.0), (2, 10.0, 20.0))
    plan = build_subtitle_plan(SubtitlePlannerInput(
        timeline=timeline,
        narration_paragraphs=["Mira stands at the edge.", "She walks into the forest."],
    ))

    assert [c.sequence_index for c in plan.cues] == [1, 2]
    assert plan.cues[0].scene_id == 1
    assert plan.cues[1].scene_id == 2
    assert plan.cues[0].end_time == 10.0
    assert plan.cues[1].start_time == 10.0


def test_empty_narration_paragraphs_yields_no_cues():
    timeline = _timeline((1, 0.0, 10.0))
    plan = build_subtitle_plan(SubtitlePlannerInput(timeline=timeline, narration_paragraphs=[]))

    assert plan.cues == []
    assert plan.source_timeline_id == "tl-1"


def test_paragraph_count_mismatch_rejected():
    timeline = _timeline((1, 0.0, 10.0), (2, 10.0, 20.0))
    with pytest.raises(ContractViolationError):
        build_subtitle_plan(SubtitlePlannerInput(timeline=timeline, narration_paragraphs=["Only one paragraph."]))


def test_overlapping_voice_segments_rejected():
    timeline = _timeline((1, 0.0, 10.0), (2, 5.0, 15.0))  # scene 2 starts before scene 1 ends
    with pytest.raises(ContractViolationError):
        build_subtitle_plan(SubtitlePlannerInput(
            timeline=timeline,
            narration_paragraphs=["Mira stands at the edge.", "She walks into the forest."],
        ))


def test_zero_length_voice_segment_produces_no_cues_for_that_scene():
    timeline = _timeline((1, 0.0, 0.0), (2, 0.0, 10.0))
    plan = build_subtitle_plan(SubtitlePlannerInput(
        timeline=timeline,
        narration_paragraphs=["Skipped scene.", "Mira walks forward."],
    ))

    assert [c.scene_id for c in plan.cues] == [2]

import re
from typing import List, Tuple

from agents.base.exceptions import ContractViolationError
from agents.subtitle_planner.contract import SubtitlePlannerInput
from shared_core.contracts.subtitle import SubtitleCue, SubtitlePlan

# Standard subtitle readability ceiling (two ~42-char lines) - long sentences
# get word-wrapped under this instead of running as one oversized cue.
MAX_CUE_CHARS = 84

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> List[str]:
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text.strip() else []


def _wrap_to_max_chars(sentence: str, max_chars: int) -> List[str]:
    words = sentence.split()
    segments: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        added_len = len(word) + (1 if current else 0)
        if current and current_len + added_len > max_chars:
            segments.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += added_len
    if current:
        segments.append(" ".join(current))
    return segments


def _segment_narration(text: str) -> List[str]:
    """Splits one scene's narration paragraph into readable subtitle
    segments: sentence boundaries first, then word-wrapped further if a
    sentence alone still exceeds MAX_CUE_CHARS."""
    segments: List[str] = []
    for sentence in _split_sentences(text):
        segments.extend(_wrap_to_max_chars(sentence, MAX_CUE_CHARS))
    return segments


def _allocate_cue_timings(segments: List[str], start: float, end: float) -> List[Tuple[str, float, float]]:
    """Distributes a scene's narration window across its segments,
    proportional to each segment's character count - a longer segment holds
    the screen longer. The final segment's end is pinned exactly to the
    window's end so float rounding never leaves a gap or overlap at the
    scene boundary."""
    total_chars = sum(len(s) for s in segments) or 1
    window = end - start
    cursor = start
    timed: List[Tuple[str, float, float]] = []
    for i, segment in enumerate(segments):
        if i == len(segments) - 1:
            segment_end = end
        else:
            share = len(segment) / total_chars
            segment_end = cursor + window * share
        timed.append((segment, cursor, segment_end))
        cursor = segment_end
    return timed


def _validate_no_overlaps(cues: List[SubtitleCue]) -> None:
    for cue in cues:
        if cue.end_time < cue.start_time:
            raise ContractViolationError(
                f"Subtitle cue {cue.sequence_index} has end_time ({cue.end_time}) before "
                f"start_time ({cue.start_time})"
            )
    for prev, nxt in zip(cues, cues[1:]):
        if nxt.start_time < prev.end_time:
            raise ContractViolationError(
                f"Subtitle cues {prev.sequence_index} and {nxt.sequence_index} overlap "
                f"({prev.end_time} > {nxt.start_time})"
            )


def build_subtitle_plan(input_data: SubtitlePlannerInput) -> SubtitlePlan:
    """Segments each scene's narration text and times the segments against
    Timeline's already-computed voice_segments - the entry point for
    Producer Studio's Subtitle Planning stage (ARCHITECTURE.md SS6/SS12).

    Runs no LLM and makes no creative decisions: sentence/word-wrap
    segmentation and proportional-by-length timing are the only rules
    applied. narration_paragraphs and timeline.voice_segments are expected to
    already be in matching, ascending scene_id order (both are derived from
    the same ascending scene sequence upstream), so they're paired
    positionally rather than by re-sorting - a count mismatch is treated as a
    contract violation rather than silently guessed at."""
    timeline = input_data.timeline
    paragraphs = input_data.narration_paragraphs

    if paragraphs and len(paragraphs) != len(timeline.voice_segments):
        raise ContractViolationError(
            f"Narration text has {len(paragraphs)} scene paragraph(s) but Timeline has "
            f"{len(timeline.voice_segments)} voice segment(s) - Subtitle Planning requires "
            f"exactly one paragraph per voice segment, or none at all when the Voice Script "
            f"stage was skipped"
        )

    cues: List[SubtitleCue] = []
    sequence_index = 1
    for segment, paragraph in zip(timeline.voice_segments, paragraphs):
        if segment.end_time <= segment.start_time:
            continue
        for text, start, end in _allocate_cue_timings(_segment_narration(paragraph), segment.start_time, segment.end_time):
            cues.append(SubtitleCue(
                sequence_index=sequence_index,
                scene_id=segment.scene_id,
                text=text,
                start_time=start,
                end_time=end,
            ))
            sequence_index += 1

    _validate_no_overlaps(cues)

    return SubtitlePlan(
        source_timeline_id=timeline.timeline_id,
        cues=cues,
        total_duration_seconds=timeline.total_duration_seconds,
    )

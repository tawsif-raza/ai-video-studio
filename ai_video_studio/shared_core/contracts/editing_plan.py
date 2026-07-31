import uuid
from datetime import UTC, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# Duration of the crossfade execution_engine/filter_graph_builder.py applies
# at every scene-boundary transition (its own CROSSFADE_SECONDS). Duplicated
# here rather than imported - shared_core may not depend on execution_engine
# (ARCHITECTURE.md SS19) - and kept honest by
# tests/integration/test_editing_plan_duration_matches_render.py, which
# renders a real multi-scene clip through actual ffmpeg and asserts ffprobe's
# measured duration matches compute_final_duration_seconds(), a stronger
# guarantee than sharing the constant would give since it checks the real
# rendered artifact, not just that two numbers happen to agree.
_CROSSFADE_SECONDS = 0.75


class EditingSegment(BaseModel):
    """One clip's placement in the final edit. Carries the resolved
    asset_path/asset_type/timing straight from its Timeline clip, plus
    references into the other Producer Package artifacts rather than
    duplicating their content: subtitle_cue_indices are SubtitleCue.sequence_index
    values (subtitle_plan.json already has the text/timing), and
    music_cue_scene_id is a foreign key into music_plan.json's per-scene cues.
    effects_placeholders name a future effects stage's work without applying
    anything here."""

    scene_id: int
    shot_id: int
    asset_path: Optional[str] = None
    asset_type: str  # "image" | "video" | "black"
    start_time: float
    end_time: float
    subtitle_cue_indices: List[int] = Field(default_factory=list)
    music_cue_scene_id: int
    transition_in: str  # "fade_from_black" | "crossfade" | "cut"
    transition_out: str  # "fade_to_black" | "crossfade" | "cut"
    effects_placeholders: List[str] = Field(default_factory=list)


class EditingPlan(BaseModel):
    """Public output contract (ARCHITECTURE.md SS6/SS12) - Producer Package's
    editing_plan.json. The deterministic blueprint a later, still-unimplemented
    stage (FFmpeg Export) executes against - no rendering, mixing, or
    subtitle burning happens here."""

    editing_plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_timeline_id: str = ""
    source_subtitle_plan_id: str = ""
    source_music_plan_id: str = ""
    segments: List[EditingSegment] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def compute_final_duration_seconds(segments: List[EditingSegment]) -> float:
    """The actual runtime a render of these segments will produce - always
    less than or equal to the raw sum of each segment's own duration whenever
    a crossfade transition is present, since a crossfade overlaps (and so
    shrinks) the two clips on either side of it rather than playing them back
    to back.

    This is what EditingPlan.total_duration_seconds must hold: it previously
    held the Timeline's raw, contiguous sum instead (segments' own start/end
    times, which do not reserve any crossfade overlap), so postflight
    validation - which compares the rendered file's real duration against
    total_duration_seconds - failed by design for every project using a
    scene-boundary crossfade (Release-Prep milestone, following D4 cloud
    validation)."""
    if not segments:
        return 0.0

    chain_durations: List[float] = []
    current = segments[0].end_time - segments[0].start_time
    for prev, nxt in zip(segments, segments[1:]):
        nxt_duration = nxt.end_time - nxt.start_time
        if prev.transition_out == "crossfade":
            chain_durations.append(current)
            current = nxt_duration
        else:
            current += nxt_duration
    chain_durations.append(current)

    total = chain_durations[0]
    for chain_duration in chain_durations[1:]:
        overlap = min(_CROSSFADE_SECONDS, total / 2, chain_duration / 2)
        total = total + chain_duration - overlap
    return total

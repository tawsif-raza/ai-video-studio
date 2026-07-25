import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


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
    asset_path: str
    asset_type: str  # "image" | "video"
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
    generated_at: datetime = Field(default_factory=datetime.utcnow)

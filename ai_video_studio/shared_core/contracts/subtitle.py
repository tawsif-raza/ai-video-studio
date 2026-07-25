import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class SubtitleCue(BaseModel):
    """One subtitle's text and screen time. sequence_index, start_time,
    end_time, and text are deliberately the entire shape - it's exactly what
    an SRT or VTT writer (a future milestone) needs to serialize a cue
    directly, with no further lookups."""

    sequence_index: int
    scene_id: int
    text: str
    start_time: float
    end_time: float


class SubtitlePlan(BaseModel):
    """Public output contract (ARCHITECTURE.md SS6/SS12) - Producer Package's
    subtitle_plan.json. Cues are ordered by sequence_index, non-overlapping,
    and timed against the same clock as Timeline's clips/voice_segments."""

    subtitle_plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_timeline_id: str = ""
    cues: List[SubtitleCue] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)

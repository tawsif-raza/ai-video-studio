import uuid
from datetime import UTC, datetime
from typing import List

from pydantic import BaseModel, Field


class SceneMood(BaseModel):
    """One scene's mood, read from the Production Package's scene_plan.json -
    a small typed record rather than a full reconstructed ProductionPlan,
    the same convention ShotDuration established for Timeline Planning:
    Producer Studio reads only the one field a stage needs directly off the
    already-written Production Package deliverable."""

    scene_id: int
    mood: str


class DuckWindow(BaseModel):
    """One window during which music should duck under narration - one per
    subtitle cue in the scene, not one blanket window per scene, so music can
    stay at full volume in any gap between spoken lines."""

    start_time: float
    end_time: float


class MusicCue(BaseModel):
    """One scene's music strategy - not an audio file, a structured plan for
    a later, still-unimplemented stage (music generation/selection + FFmpeg
    mixing) to execute against. tempo/intensity are "none" and duck_windows
    is empty whenever is_silent is True - there is no music to duck or fade
    in a silent cue."""

    scene_id: int
    start_time: float
    end_time: float
    mood: str
    tempo: str
    intensity: str
    is_silent: bool = False
    fade_in_seconds: float = 0.0
    fade_out_seconds: float = 0.0
    duck_windows: List[DuckWindow] = Field(default_factory=list)


class MusicPlan(BaseModel):
    """Public output contract (ARCHITECTURE.md SS6/SS12) - Producer Package's
    music_plan.json. Carries strategy only: no audio file paths, no actual
    generated/downloaded music, no mixed output - those are later stages'
    jobs (Music Generation/Selection, FFmpeg Export)."""

    music_plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_timeline_id: str = ""
    cues: List[MusicCue] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ShotDuration(BaseModel):
    """One shot's planned duration, read from the Production Package's
    shot_plan.json rather than re-deriving a full ShotPlan object - that's the
    durable, reloadable form this data takes once Director Studio has already
    finished and exited (ARCHITECTURE.md SS6: Producer Studio's input is the
    Production Package's contents)."""

    scene_id: int
    shot_id: int
    duration_seconds: int


class TimelineClip(BaseModel):
    """One shot's placement on the master timeline. asset_path is whichever of
    the shot's approved image/video asset was chosen - video is preferred over
    a static image when both exist (ARCHITECTURE.md SS6: Timeline Planning
    sequences validated assets, it does not generate or choose media itself
    beyond this one ordering decision)."""

    scene_id: int
    shot_id: int
    asset_path: str
    asset_type: str  # "image" | "video"
    duration_seconds: int
    start_time: float
    end_time: float


class VoiceSegment(BaseModel):
    """The time window one scene's narration occupies on the timeline, derived
    from that scene's clips - not from decoding the narration audio file itself
    (ARCHITECTURE.md SS6: only FFmpeg Export is sanctioned to do real media
    I/O). This is the interface Subtitle Planning consumes next to time-align
    voice_script.txt's text to the timeline."""

    scene_id: int
    start_time: float
    end_time: float
    audio_path: str


class Timeline(BaseModel):
    """Public output contract (ARCHITECTURE.md SS6/SS12) - Producer Package's
    timeline_plan.json. Deliberately carries only sequencing/timing: no
    subtitle text, no music cues, no edit instructions - those are Subtitle
    Planning, Music Planning, and Editing Plan's own responsibilities, all
    consuming this Timeline as their own input."""

    timeline_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_asset_manifest_id: str = ""
    clips: List[TimelineClip] = Field(default_factory=list)
    voice_segments: List[VoiceSegment] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)

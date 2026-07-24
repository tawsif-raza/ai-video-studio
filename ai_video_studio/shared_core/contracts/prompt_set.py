import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class ShotPromptSchema(BaseModel):
    """
    Deliberately does NOT include scene_id/shot_id/duration - we already know those
    from Python, so we never ask the LLM to echo identifiers back to us. Trusting an
    LLM to correctly echo IDs is an easy, silent way for shots to get mismatched;
    Python attaches them after validation instead.
    """

    image_prompt: str = Field(..., min_length=40, description="Final, polished prompt for image generation")
    video_motion_prompt: str = Field(
        ..., min_length=15, description="Short description of motion/camera movement for video generation"
    )


class ShotPrompt(ShotPromptSchema):
    """Public output contract for a single shot - what Image/Video Generation consume."""

    scene_id: int
    shot_id: int
    duration_seconds: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class PromptSet(BaseModel):
    """The full collection of finished shot prompts for the whole storyboard."""

    prompt_set_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_storyboard_id: str = ""
    shots: List[ShotPrompt] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

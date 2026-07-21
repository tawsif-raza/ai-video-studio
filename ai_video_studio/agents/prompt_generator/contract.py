import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.schema import EnvironmentProfile
from agents.prompt_generator.schema import ShotPromptSchema


class PromptGeneratorInput(BaseModel):
    """
    Everything one shot needs, already resolved. Nothing here requires the LLM to
    look anything up - it only has to write, not reason about which data belongs
    to which shot.
    """

    scene_id: int
    shot_id: int
    shot_description: str
    camera_angle: str
    camera_movement: str
    duration_seconds: int
    character_profiles: List[CharacterVisualProfile]
    environment_profile: EnvironmentProfile
    art_style: Optional[str] = None


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

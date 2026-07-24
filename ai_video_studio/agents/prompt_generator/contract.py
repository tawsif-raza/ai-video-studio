from typing import List, Optional

from pydantic import BaseModel

from shared_core.contracts.character_sheet import CharacterVisualProfile
from shared_core.contracts.environment_sheet import EnvironmentProfile
from shared_core.contracts.prompt_set import PromptSet, ShotPrompt

__all__ = ["CharacterVisualProfile", "EnvironmentProfile", "PromptGeneratorInput", "PromptSet", "ShotPrompt"]


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

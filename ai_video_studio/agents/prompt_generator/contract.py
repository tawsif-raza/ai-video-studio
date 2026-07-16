import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
from agents.prompt_generator.schema import ShotPromptSchema
from agents.story_planner.contract import ProductionPlan


def find_environment_for_scene(
    scene_id: int, production_plan: ProductionPlan, environment_sheet: EnvironmentSheet
) -> EnvironmentProfile:
    """
    Looks up which environment profile belongs to a given scene, via the scene's
    setting string. Raises loudly rather than silently mismatching if something
    upstream was inconsistent - this should never actually fire if Scene Planner
    and Environment Planner's validators both passed.
    """
    scene = next((s for s in production_plan.scenes if s.scene_id == scene_id), None)
    if scene is None:
        raise ValueError(f"scene_id {scene_id} not found in production_plan")

    profile = next((p for p in environment_sheet.environment_profiles if p.setting == scene.setting), None)
    if profile is None:
        raise ValueError(f"No environment profile found for setting '{scene.setting}' (scene_id {scene_id})")

    return profile


def find_characters_for_shot(
    character_names: List[str], character_sheet: CharacterSheet
) -> List[CharacterVisualProfile]:
    """Looks up the visual profile for every character named in a shot's characters_in_shot."""
    profiles = [p for p in character_sheet.character_profiles if p.name in character_names]
    found_names = {p.name for p in profiles}
    missing = set(character_names) - found_names
    if missing:
        raise ValueError(f"No character profile found for: {sorted(missing)}")
    return profiles


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

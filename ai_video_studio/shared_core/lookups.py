# TODO(Phase 5): CharacterSheet/EnvironmentSheet/ProductionPlan and their nested
# schema types currently live inside agents/*/contract.py and agents/*/schema.py.
# Shared Core importing from agents/ here is a temporary compatibility layer,
# approved for Milestone B - Phase 3 (see ARCHITECTURE.md SS15, Phase 3 vs
# Phase 5). Once the Production Package schema types are relocated into
# shared_core (Phase 5), these imports must be reversed - agents should import
# from shared_core, never the other way around.

from typing import List

from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
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

from typing import List

from shared_core.contracts.camera_plan import CameraPlan, CameraShot
from shared_core.contracts.character_sheet import CharacterSheet, CharacterVisualProfile
from shared_core.contracts.environment_sheet import EnvironmentProfile, EnvironmentSheet
from shared_core.contracts.production_plan import ProductionPlan


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


def find_camera_for_shot(scene_id: int, shot_id: int, camera_plan: CameraPlan) -> CameraShot:
    """Looks up a single shot's camera treatment from Camera Planner's output,
    keyed by (scene_id, shot_id) - the same identifiers Scene/Shot Planner assigned."""
    scene = next((sp for sp in camera_plan.scene_plans if sp.scene_id == scene_id), None)
    if scene is None:
        raise ValueError(f"scene_id {scene_id} not found in camera_plan")

    shot = next((s for s in scene.shots if s.shot_id == shot_id), None)
    if shot is None:
        raise ValueError(f"shot_id {shot_id} not found in camera_plan scene {scene_id}")

    return shot

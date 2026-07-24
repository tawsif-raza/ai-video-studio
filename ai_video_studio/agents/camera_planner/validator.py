from agents.base.exceptions import ContractViolationError
from agents.camera_planner.schema import CameraPlannerSchema
from shared_core.contracts.shot_plan import ShotPlan


def validate_camera_plan(camera_plan: CameraPlannerSchema, shot_plan: ShotPlan) -> CameraPlannerSchema:
    """Validate that the CameraPlan covers the ShotPlan it was built from, one-to-one,
    and that camera language isn't lazily repeated for every single shot."""
    original_scenes = {sp.scene_id: sp for sp in shot_plan.scene_plans}
    covered_ids = [sp.scene_id for sp in camera_plan.scene_plans]

    missing = set(original_scenes) - set(covered_ids)
    if missing:
        raise ContractViolationError(f"CameraPlan is missing scene_id(s): {sorted(missing)}")

    extra = set(covered_ids) - set(original_scenes)
    if extra:
        raise ContractViolationError(f"CameraPlan references unknown scene_id(s): {sorted(extra)}")

    if len(covered_ids) != len(set(covered_ids)):
        raise ContractViolationError("CameraPlan covers the same scene_id more than once")

    all_treatments = []
    for scene_plan in camera_plan.scene_plans:
        original = original_scenes[scene_plan.scene_id]
        original_shot_ids = {shot.shot_id for shot in original.shots}
        shot_ids = [shot.shot_id for shot in scene_plan.shots]

        if len(shot_ids) != len(set(shot_ids)):
            raise ContractViolationError(f"Scene {scene_plan.scene_id}: duplicate shot_id values in CameraPlan")

        missing_shots = original_shot_ids - set(shot_ids)
        if missing_shots:
            raise ContractViolationError(
                f"Scene {scene_plan.scene_id}: CameraPlan is missing shot_id(s): {sorted(missing_shots)}"
            )

        extra_shots = set(shot_ids) - original_shot_ids
        if extra_shots:
            raise ContractViolationError(
                f"Scene {scene_plan.scene_id}: CameraPlan references unknown shot_id(s): {sorted(extra_shots)}"
            )

        for shot in scene_plan.shots:
            all_treatments.append((shot.camera_angle.strip().lower(), shot.camera_movement.strip().lower()))

    if len(all_treatments) > 2 and len(set(all_treatments)) == 1:
        raise ContractViolationError(
            "CameraPlan assigns the identical camera angle and movement to every shot - "
            "camera language must vary purposefully across a multi-shot plan"
        )

    return camera_plan

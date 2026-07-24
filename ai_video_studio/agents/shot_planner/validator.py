from agents.base.exceptions import ContractViolationError
from agents.shot_planner.schema import ShotPlannerSchema
from shared_core.contracts.storyboard import Storyboard


def validate_shot_plan(
    shot_plan: ShotPlannerSchema,
    storyboard: Storyboard,
    tolerance: float = 0.3,
) -> ShotPlannerSchema:
    """Validate that the refined ShotPlan still covers the Storyboard it was built
    from, one-to-one, without introducing camera detail or drifting off the original
    shot list (ARCHITECTURE.md SS12: Shot Planner refines narrative beats only)."""
    original_scenes = {sp.scene_id: sp for sp in storyboard.scene_plans}
    covered_ids = [sp.scene_id for sp in shot_plan.scene_plans]

    missing = set(original_scenes) - set(covered_ids)
    if missing:
        raise ContractViolationError(f"ShotPlan is missing scene_id(s): {sorted(missing)}")

    extra = set(covered_ids) - set(original_scenes)
    if extra:
        raise ContractViolationError(f"ShotPlan references unknown scene_id(s): {sorted(extra)}")

    if len(covered_ids) != len(set(covered_ids)):
        raise ContractViolationError("ShotPlan covers the same scene_id more than once")

    for scene_plan in shot_plan.scene_plans:
        original = original_scenes[scene_plan.scene_id]
        original_shots = {shot.shot_id: shot for shot in original.shots}
        shot_ids = [shot.shot_id for shot in scene_plan.shots]

        if len(shot_ids) != len(set(shot_ids)):
            raise ContractViolationError(f"Scene {scene_plan.scene_id}: duplicate shot_id values in ShotPlan")

        missing_shots = set(original_shots) - set(shot_ids)
        if missing_shots:
            raise ContractViolationError(
                f"Scene {scene_plan.scene_id}: ShotPlan is missing shot_id(s): {sorted(missing_shots)}"
            )

        extra_shots = set(shot_ids) - set(original_shots)
        if extra_shots:
            raise ContractViolationError(
                f"Scene {scene_plan.scene_id}: ShotPlan references unknown shot_id(s): {sorted(extra_shots)}"
            )

        for shot in scene_plan.shots:
            original_shot = original_shots[shot.shot_id]
            allowed_characters = set(original_shot.characters_in_shot)
            unknown = set(shot.characters_in_shot) - allowed_characters
            if unknown:
                raise ContractViolationError(
                    f"Scene {scene_plan.scene_id}, shot {shot.shot_id}: ShotPlan references "
                    f"character(s) not present in the original shot: {sorted(unknown)}"
                )

            target = original_shot.duration_seconds
            lower, upper = target * (1 - tolerance), target * (1 + tolerance)
            if not lower <= shot.duration_seconds <= upper:
                raise ContractViolationError(
                    f"Scene {scene_plan.scene_id}, shot {shot.shot_id}: refined duration "
                    f"{shot.duration_seconds}s is outside [{lower:.1f}s, {upper:.1f}s] of the "
                    f"original {target}s"
                )

    return shot_plan

from agents.base.exceptions import ContractViolationError
from agents.scene_planner.schema import ScenePlannerSchema
from shared_core.contracts.production_plan import ProductionPlan


def validate_scene_plan(
    storyboard: ScenePlannerSchema,
    production_plan: ProductionPlan,
    tolerance: float = 0.3,
) -> ScenePlannerSchema:
    """Validate that a storyboard faithfully covers its production plan."""
    original_scenes = {s.scene_id: s for s in production_plan.scenes}
    covered_ids = [sp.scene_id for sp in storyboard.scene_plans]

    missing = set(original_scenes) - set(covered_ids)
    if missing:
        raise ContractViolationError(f"Storyboard is missing scene_id(s): {sorted(missing)}")

    extra = set(covered_ids) - set(original_scenes)
    if extra:
        raise ContractViolationError(f"Storyboard references unknown scene_id(s): {sorted(extra)}")

    if len(covered_ids) != len(set(covered_ids)):
        raise ContractViolationError("Storyboard covers the same scene_id more than once")

    for scene_plan in storyboard.scene_plans:
        original = original_scenes[scene_plan.scene_id]
        if not scene_plan.shots:
            raise ContractViolationError(f"Scene {scene_plan.scene_id} has zero shots")

        shot_ids = [shot.shot_id for shot in scene_plan.shots]
        if len(shot_ids) != len(set(shot_ids)):
            raise ContractViolationError(f"Scene {scene_plan.scene_id} has duplicate shot_id values")

        allowed_characters = set(original.characters_present)
        for shot in scene_plan.shots:
            unknown = set(shot.characters_in_shot) - allowed_characters
            if unknown:
                raise ContractViolationError(
                    f"Scene {scene_plan.scene_id}, shot {shot.shot_id} references "
                    f"character(s) not present in the scene: {sorted(unknown)}"
                )

        shot_total = sum(shot.duration_seconds for shot in scene_plan.shots)
        target = original.estimated_duration_seconds
        lower, upper = target * (1 - tolerance), target * (1 + tolerance)
        if not lower <= shot_total <= upper:
            raise ContractViolationError(
                f"Scene {scene_plan.scene_id}: shot durations sum to {shot_total}s, "
                f"outside [{lower:.0f}s, {upper:.0f}s] for a {target}s scene"
            )

    return storyboard

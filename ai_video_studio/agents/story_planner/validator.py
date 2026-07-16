from agents.base.exceptions import ContractViolationError
from agents.story_planner.schema import StoryPlanSchema


def validate_story_plan(plan: StoryPlanSchema, target_duration: int, tolerance: float = 0.3) -> StoryPlanSchema:
    if not plan.scenes:
        raise ContractViolationError("Story plan has zero scenes")

    known_names = {c.name for c in plan.characters}
    for scene in plan.scenes:
        for name in scene.characters_present:
            if name not in known_names:
                raise ContractViolationError(
                    f"Scene {scene.scene_id} references unknown character '{name}'"
                )

    total = sum(s.estimated_duration_seconds for s in plan.scenes)
    lower, upper = target_duration * (1 - tolerance), target_duration * (1 + tolerance)
    if not (lower <= total <= upper):
        raise ContractViolationError(f"Total duration {total}s outside [{lower:.0f}, {upper:.0f}]")

    ids = [s.scene_id for s in plan.scenes]
    if len(ids) != len(set(ids)):
        raise ContractViolationError("Duplicate scene_id values found")

    return plan
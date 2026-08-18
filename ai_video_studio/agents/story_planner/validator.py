from typing import Optional

from agents.base.exceptions import ContractViolationError
from agents.story_planner.schema import StoryPlanSchema


class SceneCountMismatchError(ContractViolationError):
    """Raised only when scene_count_mode == 'custom' and the plan's actual
    scene count doesn't exactly match the user's requested value. A subtype
    of ContractViolationError (so it's caught wherever that already is,
    e.g. agents/base/base_agent.py's run()) but distinct enough for
    StoryPlannerAgent to catch specifically and retry - unlike other
    business-rule violations (duplicate ids, duration tolerance, unknown
    characters), a wrong scene count is worth a bounded self-correction
    attempt rather than an immediate hard failure."""


def validate_story_plan(
    plan: StoryPlanSchema,
    target_duration: int,
    tolerance: float = 0.3,
    scene_count_mode: str = "default",
    scene_count: Optional[int] = None,
) -> StoryPlanSchema:
    if not plan.scenes:
        raise ContractViolationError("Story plan has zero scenes")

    known_names = {c.name for c in plan.characters}
    for scene in plan.scenes:
        for name in scene.characters_present:
            if name not in known_names:
                raise ContractViolationError(
                    f"Scene {scene.scene_id} references unknown character '{name}'"
                )

    # Custom scene count is a hard requirement with priority over every
    # other scene-count-shaping signal (duration, default LLM judgment) -
    # checked before the duration-tolerance check below, which stays
    # duration-only and applies unchanged in both modes.
    if scene_count_mode == "custom" and scene_count is not None:
        actual = len(plan.scenes)
        if actual != scene_count:
            raise SceneCountMismatchError(
                f"Custom scene count requested exactly {scene_count} scenes, "
                f"but the story plan has {actual}"
            )

    total = sum(s.estimated_duration_seconds for s in plan.scenes)
    lower, upper = target_duration * (1 - tolerance), target_duration * (1 + tolerance)
    if not (lower <= total <= upper):
        raise ContractViolationError(f"Total duration {total}s outside [{lower:.0f}, {upper:.0f}]")

    ids = [s.scene_id for s in plan.scenes]
    if len(ids) != len(set(ids)):
        raise ContractViolationError("Duplicate scene_id values found")

    return plan

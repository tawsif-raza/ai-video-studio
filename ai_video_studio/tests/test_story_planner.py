import pytest

from agents.base.exceptions import ContractViolationError
from agents.story_planner.schema import CharacterBrief, SceneBrief, StoryPlanSchema
from agents.story_planner.validator import validate_story_plan


def _make_plan(scene_duration: int = 30, char_name: str = "Mira") -> StoryPlanSchema:
    return StoryPlanSchema(
        title="Test",
        logline="A test story",
        theme="courage",
        target_duration_seconds=30,
        tone="uplifting",
        characters=[
            CharacterBrief(name=char_name, role="protagonist", one_line_description="brave")
        ],
        scenes=[
            SceneBrief(
                scene_id=1,
                title="Opening",
                summary="Mira starts her journey",
                setting="forest",
                mood="hopeful",
                characters_present=[char_name],
                estimated_duration_seconds=scene_duration,
            )
        ],
    )


def test_valid_plan_passes():
    plan = _make_plan()
    validate_story_plan(plan, target_duration=30)


def test_unknown_character_rejected():
    plan = _make_plan()
    plan.scenes[0].characters_present.append("Ghost")
    with pytest.raises(ContractViolationError):
        validate_story_plan(plan, target_duration=30)


def test_duration_far_outside_tolerance_rejected():
    plan = _make_plan(scene_duration=5)
    with pytest.raises(ContractViolationError):
        validate_story_plan(plan, target_duration=60)


def test_duplicate_scene_id_rejected():
    plan = _make_plan()
    plan.scenes.append(plan.scenes[0].model_copy())
    with pytest.raises(ContractViolationError):
        validate_story_plan(plan, target_duration=30)


def test_zero_scenes_rejected():
    plan = _make_plan()
    plan.scenes = []
    with pytest.raises(ContractViolationError):
        validate_story_plan(plan, target_duration=30)

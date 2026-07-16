import pytest

from agents.base.exceptions import ContractViolationError
from agents.scene_planner.schema import ScenePlan, ScenePlannerSchema, ShotBrief
from agents.scene_planner.validator import validate_scene_plan
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief


def _make_plan():
    return ProductionPlan(
        title="Test", logline="A test", theme="courage",
        target_duration_seconds=15, tone="uplifting",
        characters=[CharacterBrief(name="Mira", role="protagonist", one_line_description="brave")],
        scenes=[
            SceneBrief(
                scene_id=1, title="Opening", summary="Mira starts",
                setting="forest", mood="hopeful",
                characters_present=["Mira"], estimated_duration_seconds=15,
            )
        ],
        source_idea="test idea",
    )


def _make_storyboard(shot_duration=15, char_name="Mira", scene_id=1):
    return ScenePlannerSchema(
        scene_plans=[
            ScenePlan(
                scene_id=scene_id,
                shots=[
                    ShotBrief(
                        shot_id=1, camera_angle="wide shot", camera_movement="static",
                        description="Mira stands in the forest",
                        characters_in_shot=[char_name], duration_seconds=shot_duration,
                    )
                ],
            )
        ]
    )


def test_valid_storyboard_passes():
    validate_scene_plan(_make_storyboard(), _make_plan())


def test_missing_scene_rejected():
    plan = _make_plan()
    storyboard = _make_storyboard(scene_id=2)
    with pytest.raises(ContractViolationError):
        validate_scene_plan(storyboard, plan)


def test_unknown_character_in_shot_rejected():
    storyboard = _make_storyboard(char_name="Ghost")
    with pytest.raises(ContractViolationError):
        validate_scene_plan(storyboard, _make_plan())


def test_shot_duration_mismatch_rejected():
    storyboard = _make_storyboard(shot_duration=2)
    with pytest.raises(ContractViolationError):
        validate_scene_plan(storyboard, _make_plan())
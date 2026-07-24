import pytest

from agents.base.exceptions import ContractViolationError
from agents.shot_planner.schema import ShotItem, ShotPlannerSchema, ShotScenePlan
from agents.shot_planner.validator import validate_shot_plan
from shared_core.contracts.storyboard import ScenePlan, ShotBrief, Storyboard


def _make_storyboard(shot_duration=15, char_name="Mira", scene_id=1, shot_id=1):
    return Storyboard(
        scene_plans=[
            ScenePlan(
                scene_id=scene_id,
                shots=[
                    ShotBrief(
                        shot_id=shot_id,
                        description="Mira stands in the forest",
                        characters_in_shot=[char_name], duration_seconds=shot_duration,
                    )
                ],
            )
        ]
    )


def _make_shot_plan(shot_duration=15, char_name="Mira", scene_id=1, shot_id=1):
    return ShotPlannerSchema(
        scene_plans=[
            ShotScenePlan(
                scene_id=scene_id,
                shots=[
                    ShotItem(
                        shot_id=shot_id,
                        description="Mira stands in the forest, resolute",
                        characters_in_shot=[char_name], duration_seconds=shot_duration,
                    )
                ],
            )
        ]
    )


def test_valid_shot_plan_passes():
    validate_shot_plan(_make_shot_plan(), _make_storyboard())


def test_missing_scene_rejected():
    storyboard = _make_storyboard(scene_id=1)
    shot_plan = _make_shot_plan(scene_id=2)
    with pytest.raises(ContractViolationError):
        validate_shot_plan(shot_plan, storyboard)


def test_missing_shot_rejected():
    storyboard = _make_storyboard(shot_id=1)
    shot_plan = _make_shot_plan(shot_id=2)
    with pytest.raises(ContractViolationError):
        validate_shot_plan(shot_plan, storyboard)


def test_unknown_character_in_shot_rejected():
    storyboard = _make_storyboard(char_name="Mira")
    shot_plan = _make_shot_plan(char_name="Ghost")
    with pytest.raises(ContractViolationError):
        validate_shot_plan(shot_plan, storyboard)


def test_duration_drift_beyond_tolerance_rejected():
    storyboard = _make_storyboard(shot_duration=15)
    shot_plan = _make_shot_plan(shot_duration=2)
    with pytest.raises(ContractViolationError):
        validate_shot_plan(shot_plan, storyboard)

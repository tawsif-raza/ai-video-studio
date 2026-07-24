import pytest

from agents.base.exceptions import ContractViolationError
from agents.camera_planner.schema import CameraPlannerSchema, CameraScenePlan, CameraShot
from agents.camera_planner.validator import validate_camera_plan
from shared_core.contracts.shot_plan import ShotItem, ShotPlan, ShotScenePlan


def _make_shot_plan(scene_id=1, shot_ids=(1, 2)):
    return ShotPlan(
        scene_plans=[
            ShotScenePlan(
                scene_id=scene_id,
                shots=[
                    ShotItem(
                        shot_id=shot_id,
                        description=f"Shot {shot_id}",
                        characters_in_shot=["Mira"], duration_seconds=5,
                    )
                    for shot_id in shot_ids
                ],
            )
        ]
    )


def _make_camera_plan(scene_id=1, shots=((1, "wide shot", "static"), (2, "close-up", "slow zoom in"))):
    return CameraPlannerSchema(
        scene_plans=[
            CameraScenePlan(
                scene_id=scene_id,
                shots=[
                    CameraShot(shot_id=shot_id, camera_angle=angle, camera_movement=movement)
                    for shot_id, angle, movement in shots
                ],
            )
        ]
    )


def test_valid_camera_plan_passes():
    validate_camera_plan(_make_camera_plan(), _make_shot_plan())


def test_missing_scene_rejected():
    shot_plan = _make_shot_plan(scene_id=1)
    camera_plan = _make_camera_plan(scene_id=2)
    with pytest.raises(ContractViolationError):
        validate_camera_plan(camera_plan, shot_plan)


def test_missing_shot_rejected():
    shot_plan = _make_shot_plan(shot_ids=(1, 2, 3))
    camera_plan = _make_camera_plan(shots=((1, "wide shot", "static"), (2, "close-up", "slow zoom in")))
    with pytest.raises(ContractViolationError):
        validate_camera_plan(camera_plan, shot_plan)


def test_extra_shot_rejected():
    shot_plan = _make_shot_plan(shot_ids=(1,))
    camera_plan = _make_camera_plan(shots=((1, "wide shot", "static"), (2, "close-up", "slow zoom in")))
    with pytest.raises(ContractViolationError):
        validate_camera_plan(camera_plan, shot_plan)


def test_identical_camera_language_across_all_shots_rejected():
    shot_plan = _make_shot_plan(shot_ids=(1, 2, 3))
    camera_plan = _make_camera_plan(
        shots=((1, "wide shot", "static"), (2, "wide shot", "static"), (3, "wide shot", "static"))
    )
    with pytest.raises(ContractViolationError):
        validate_camera_plan(camera_plan, shot_plan)


def test_two_identical_shots_allowed():
    """Two shots sharing framing (e.g. shot-reverse-shot) isn't inherently lazy -
    only 3+ identical shots trip the 'vary camera language' rule."""
    shot_plan = _make_shot_plan(shot_ids=(1, 2))
    camera_plan = _make_camera_plan(shots=((1, "wide shot", "static"), (2, "wide shot", "static")))
    validate_camera_plan(camera_plan, shot_plan)

import json

import pytest

from agents.base.exceptions import ContractViolationError
from agents.story_planner.agent import StoryPlannerAgent
from agents.story_planner.contract import StoryPlannerInput
from agents.story_planner.schema import CharacterBrief, SceneBrief, StoryPlanSchema
from agents.story_planner.validator import SceneCountMismatchError, validate_story_plan
from tests.integration.test_pipeline import FakeLLMClient


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


def test_default_mode_ignores_scene_count_even_if_provided():
    """scene_count_mode='default' must never enforce an exact scene count -
    the pre-existing LLM-judged behavior is untouched, regardless of what
    scene_count happens to be set to (it should always be None in practice,
    enforced at the web_api boundary, but the validator itself must not
    depend on that)."""
    plan = _make_plan()  # exactly 1 scene
    validate_story_plan(plan, target_duration=30, scene_count_mode="default", scene_count=99)


def test_custom_mode_matching_count_passes():
    plan = _make_plan()  # exactly 1 scene
    validate_story_plan(plan, target_duration=30, scene_count_mode="custom", scene_count=1)


def test_custom_mode_mismatched_count_raises_scene_count_mismatch():
    plan = _make_plan()  # exactly 1 scene
    with pytest.raises(SceneCountMismatchError):
        validate_story_plan(plan, target_duration=30, scene_count_mode="custom", scene_count=5)


def _n_scene_story_response(scene_count: int, duration: int, char_name: str = "Mira") -> str:
    per_scene = duration // scene_count
    return json.dumps(
        {
            "title": "Test Story",
            "logline": "A test story for pipeline verification",
            "theme": "courage",
            "target_duration_seconds": duration,
            "tone": "uplifting",
            "characters": [{"name": char_name, "role": "protagonist", "one_line_description": "A brave explorer"}],
            "scenes": [
                {
                    "scene_id": i,
                    "title": f"Scene {i}",
                    "summary": f"Beat {i} of the journey",
                    "setting": "forest",
                    "mood": "hopeful",
                    "characters_present": [char_name],
                    "estimated_duration_seconds": per_scene,
                }
                for i in range(1, scene_count + 1)
            ],
        }
    )


def test_custom_scene_count_hard_requirement_end_to_end():
    """The story_idea/duration alone would nudge the model toward its usual
    default scene count - proving the agent still lands on the exact
    user-requested count when scene_count_mode='custom' is the point of
    this feature (task section 4/6's HARD OVERRIDE rule)."""
    fake_llm = FakeLLMClient([_n_scene_story_response(scene_count=10, duration=150)])
    agent = StoryPlannerAgent(fake_llm)

    result = agent.run(
        StoryPlannerInput(
            story_idea="A brave explorer",
            target_duration_seconds=150,
            scene_count_mode="custom",
            scene_count=10,
        )
    )

    assert result.success, result.error
    assert len(result.data.scenes) == 10
    assert result.data.scene_count_mode == "custom"
    assert result.data.scene_count == 10


def test_custom_scene_count_retries_and_self_corrects_on_mismatch():
    """Section 8's 'do not trust the LLM to follow the instruction' - a
    first attempt that returns the wrong count must not fail the run
    outright; StoryPlannerAgent retries with a correction note and succeeds
    once the model gets it right."""
    fake_llm = FakeLLMClient(
        [
            _n_scene_story_response(scene_count=3, duration=150),  # wrong: requested 10
            _n_scene_story_response(scene_count=10, duration=150),  # correct on retry
        ]
    )
    agent = StoryPlannerAgent(fake_llm)

    result = agent.run(
        StoryPlannerInput(
            story_idea="A brave explorer",
            target_duration_seconds=150,
            scene_count_mode="custom",
            scene_count=10,
        )
    )

    assert result.success, result.error
    assert len(result.data.scenes) == 10


def test_custom_scene_count_fails_after_exhausting_retries():
    """Every attempt keeps missing -> the run must fail loudly (existing
    ContractViolationError-driven failure path), never silently accept a
    wrong count."""
    from config import settings

    wrong_responses = [
        _n_scene_story_response(scene_count=3, duration=150) for _ in range(settings.MAX_RETRIES)
    ]
    fake_llm = FakeLLMClient(wrong_responses)
    agent = StoryPlannerAgent(fake_llm)

    result = agent.run(
        StoryPlannerInput(
            story_idea="A brave explorer",
            target_duration_seconds=150,
            scene_count_mode="custom",
            scene_count=10,
        )
    )

    assert not result.success
    assert "10" in result.error and "3" in result.error


def test_unrelated_contract_violation_is_not_retried():
    """Only a scene-count mismatch is worth retrying - a different
    violation (here: zero scenes) must still fail on the first attempt,
    exactly as it always has."""
    empty_scenes_response = json.dumps(
        {
            "title": "Broken",
            "logline": "no scenes",
            "theme": "n/a",
            "target_duration_seconds": 150,
            "tone": "n/a",
            "characters": [],
            "scenes": [],
        }
    )
    fake_llm = FakeLLMClient([empty_scenes_response])
    agent = StoryPlannerAgent(fake_llm)

    result = agent.run(
        StoryPlannerInput(
            story_idea="A brave explorer",
            target_duration_seconds=150,
            scene_count_mode="custom",
            scene_count=10,
        )
    )

    assert not result.success
    assert "zero scenes" in result.error

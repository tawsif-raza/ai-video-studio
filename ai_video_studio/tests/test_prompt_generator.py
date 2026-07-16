import pytest

from agents.base.exceptions import ContractViolationError
from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
from agents.prompt_generator.contract import find_characters_for_shot, find_environment_for_scene
from agents.prompt_generator.schema import ShotPromptSchema
from agents.prompt_generator.validator import validate_shot_prompt
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
                setting="Forest clearing", mood="hopeful",
                characters_present=["Mira"], estimated_duration_seconds=15,
            )
        ],
        source_idea="test idea",
    )


def _make_character_sheet():
    return CharacterSheet(
        character_profiles=[
            CharacterVisualProfile(
                name="Mira", age_range="mid-20s", build="lean", face_details="warm eyes",
                hair="black hair", outfit="green tunic", color_palette=["green", "brown"],
                distinguishing_features="a scar", art_style_keywords=["3D animated"],
                reference_prompt="A lean young woman with black hair and warm eyes in a green tunic.",
            )
        ]
    )


def _make_environment_sheet(setting="Forest clearing"):
    return EnvironmentSheet(
        environment_profiles=[
            EnvironmentProfile(
                setting=setting, time_of_day="dawn", weather="misty",
                key_visual_elements=["tall trees"], color_palette=["green", "grey"],
                lighting="soft morning light", atmosphere="peaceful",
                art_style_keywords=["3D animated"],
                reference_prompt="A misty forest clearing at dawn with tall trees and soft morning light.",
            )
        ]
    )


def test_find_environment_for_scene_success():
    profile = find_environment_for_scene(1, _make_plan(), _make_environment_sheet())
    assert profile.setting == "Forest clearing"


def test_find_environment_for_scene_missing_raises():
    with pytest.raises(ValueError):
        find_environment_for_scene(1, _make_plan(), _make_environment_sheet(setting="Different place"))


def test_find_characters_for_shot_success():
    profiles = find_characters_for_shot(["Mira"], _make_character_sheet())
    assert len(profiles) == 1
    assert profiles[0].name == "Mira"


def test_find_characters_for_shot_missing_raises():
    with pytest.raises(ValueError):
        find_characters_for_shot(["Ghost"], _make_character_sheet())


def test_valid_shot_prompt_passes():
    prompt = ShotPromptSchema(
        image_prompt="A lean young woman with black hair stands in a misty forest clearing at dawn, "
                      "warm morning light filtering through tall trees.",
        video_motion_prompt="She slowly turns her head toward the light as the camera pans right.",
    )
    validate_shot_prompt(prompt)


def test_identical_prompts_rejected():
    same_text = "A lean young woman stands in a misty forest clearing at dawn under tall trees."
    prompt = ShotPromptSchema(image_prompt=same_text, video_motion_prompt=same_text)
    with pytest.raises(ContractViolationError):
        validate_shot_prompt(prompt)

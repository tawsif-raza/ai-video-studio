import pytest

from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief
from shared_core.lookups import find_characters_for_shot, find_environment_for_scene


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

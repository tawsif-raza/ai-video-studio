import pytest

from agents.base.exceptions import ContractViolationError
from agents.environment_planner.contract import get_unique_settings
from agents.environment_planner.schema import EnvironmentPlannerSchema, EnvironmentProfile
from agents.environment_planner.validator import validate_environment_sheet
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief


def _make_plan(settings_list=("Rooftop party", "Rooftop party", "Dance floor")):
    return ProductionPlan(
        title="Test", logline="A test", theme="courage",
        target_duration_seconds=30, tone="uplifting",
        characters=[CharacterBrief(name="Mira", role="protagonist", one_line_description="brave")],
        scenes=[
            SceneBrief(
                scene_id=i + 1, title=f"Scene {i + 1}", summary="Something happens",
                setting=setting, mood="hopeful",
                characters_present=["Mira"], estimated_duration_seconds=10,
            )
            for i, setting in enumerate(settings_list)
        ],
        source_idea="test idea",
    )


def _make_env_profile(setting="Rooftop party"):
    return EnvironmentProfile(
        setting=setting, time_of_day="sunset", weather="clear",
        key_visual_elements=["string lights", "potted plants"],
        color_palette=["warm orange", "deep blue"],
        lighting="golden hour glow", atmosphere="lively and warm",
        art_style_keywords=["3D animated", "Pixar-style"],
        reference_prompt="A bustling rooftop party at sunset with string lights and potted plants, "
                          "warm orange and deep blue tones, 3D animated Pixar-style.",
    )


def test_get_unique_settings_dedupes_and_preserves_order():
    plan = _make_plan(settings_list=("Rooftop party", "Rooftop party", "Dance floor"))
    assert get_unique_settings(plan) == ["Rooftop party", "Dance floor"]


def test_valid_environment_sheet_passes():
    plan = _make_plan(settings_list=("Rooftop party",))
    sheet = EnvironmentPlannerSchema(environment_profiles=[_make_env_profile("Rooftop party")])
    validate_environment_sheet(sheet, plan)


def test_missing_setting_rejected():
    plan = _make_plan(settings_list=("Rooftop party", "Dance floor"))
    sheet = EnvironmentPlannerSchema(environment_profiles=[_make_env_profile("Rooftop party")])
    with pytest.raises(ContractViolationError):
        validate_environment_sheet(sheet, plan)


def test_unknown_setting_rejected():
    plan = _make_plan(settings_list=("Rooftop party",))
    sheet = EnvironmentPlannerSchema(environment_profiles=[_make_env_profile("Basement")])
    with pytest.raises(ContractViolationError):
        validate_environment_sheet(sheet, plan)


def test_duplicate_setting_profile_rejected():
    plan = _make_plan(settings_list=("Rooftop party",))
    sheet = EnvironmentPlannerSchema(
        environment_profiles=[_make_env_profile("Rooftop party"), _make_env_profile("Rooftop party")]
    )
    with pytest.raises(ContractViolationError):
        validate_environment_sheet(sheet, plan)
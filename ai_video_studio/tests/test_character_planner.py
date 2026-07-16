import pytest

from agents.base.exceptions import ContractViolationError
from agents.character_planner.schema import CharacterPlannerSchema, CharacterVisualProfile
from agents.character_planner.validator import validate_character_sheet
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief


def _make_plan(character_names=("Mira",)):
    return ProductionPlan(
        title="Test", logline="A test", theme="courage",
        target_duration_seconds=15, tone="uplifting",
        characters=[
            CharacterBrief(name=n, role="protagonist", one_line_description="brave")
            for n in character_names
        ],
        scenes=[
            SceneBrief(
                scene_id=1, title="Opening", summary="Mira starts",
                setting="forest", mood="hopeful",
                characters_present=list(character_names), estimated_duration_seconds=15,
            )
        ],
        source_idea="test idea",
    )


def _make_profile(name="Mira"):
    return CharacterVisualProfile(
        name=name, age_range="mid-20s", build="lean and agile",
        face_details="round face, warm brown eyes", hair="short black hair",
        outfit="green forest tunic", color_palette=["forest green", "earth brown"],
        distinguishing_features="a small scar above her left eyebrow",
        art_style_keywords=["3D animated", "Pixar-style"],
        reference_prompt="A lean, agile young woman in her mid-20s with short black hair, "
                          "warm brown eyes, wearing a green forest tunic, 3D animated Pixar-style.",
    )


def test_valid_character_sheet_passes():
    sheet = CharacterPlannerSchema(character_profiles=[_make_profile()])
    validate_character_sheet(sheet, _make_plan())


def test_missing_character_rejected():
    plan = _make_plan(character_names=("Mira", "Kofi"))
    sheet = CharacterPlannerSchema(character_profiles=[_make_profile("Mira")])
    with pytest.raises(ContractViolationError):
        validate_character_sheet(sheet, plan)


def test_unknown_character_rejected():
    sheet = CharacterPlannerSchema(character_profiles=[_make_profile("Ghost")])
    with pytest.raises(ContractViolationError):
        validate_character_sheet(sheet, _make_plan())


def test_duplicate_profile_rejected():
    sheet = CharacterPlannerSchema(character_profiles=[_make_profile(), _make_profile()])
    with pytest.raises(ContractViolationError):
        validate_character_sheet(sheet, _make_plan())
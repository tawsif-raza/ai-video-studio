import pytest

from agents.base.exceptions import ContractViolationError
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief
from agents.voice_script.schema import NarrationLine, VoiceScriptSchema
from agents.voice_script.validator import validate_voice_script


def _make_plan(scene_ids=(1, 2)):
    return ProductionPlan(
        title="Test", logline="A test", theme="courage",
        target_duration_seconds=60, tone="uplifting",
        characters=[CharacterBrief(name="Mira", role="protagonist", one_line_description="brave")],
        scenes=[
            SceneBrief(
                scene_id=scene_id, title=f"Scene {scene_id}", summary="Something happens",
                setting="Forest clearing", mood="hopeful",
                characters_present=["Mira"], estimated_duration_seconds=30,
            )
            for scene_id in scene_ids
        ],
        source_idea="test idea",
    )


def _make_script(lines):
    return VoiceScriptSchema(lines=lines)


def test_valid_script_passes():
    plan = _make_plan(scene_ids=(1, 2))
    script = _make_script([
        NarrationLine(scene_id=1, narration_text="Mira steps into the clearing."),
        NarrationLine(scene_id=2, narration_text="She presses onward."),
    ])
    validate_voice_script(script, plan)


def test_missing_scene_rejected():
    plan = _make_plan(scene_ids=(1, 2))
    script = _make_script([
        NarrationLine(scene_id=1, narration_text="Mira steps into the clearing."),
    ])
    with pytest.raises(ContractViolationError):
        validate_voice_script(script, plan)


def test_unknown_scene_rejected():
    plan = _make_plan(scene_ids=(1,))
    script = _make_script([
        NarrationLine(scene_id=1, narration_text="Mira steps into the clearing."),
        NarrationLine(scene_id=2, narration_text="An unplanned scene."),
    ])
    with pytest.raises(ContractViolationError):
        validate_voice_script(script, plan)


def test_duplicate_scene_rejected():
    plan = _make_plan(scene_ids=(1,))
    script = _make_script([
        NarrationLine(scene_id=1, narration_text="Mira steps into the clearing."),
        NarrationLine(scene_id=1, narration_text="Again, somehow."),
    ])
    with pytest.raises(ContractViolationError):
        validate_voice_script(script, plan)


def test_empty_narration_text_rejected():
    plan = _make_plan(scene_ids=(1,))
    script = _make_script([
        NarrationLine(scene_id=1, narration_text="   "),
    ])
    with pytest.raises(ContractViolationError):
        validate_voice_script(script, plan)

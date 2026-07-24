from agents.base.exceptions import ContractViolationError
from shared_core.contracts.production_plan import ProductionPlan
from agents.voice_script.schema import VoiceScriptSchema


def validate_voice_script(
    voice_script: VoiceScriptSchema,
    production_plan: ProductionPlan,
) -> VoiceScriptSchema:
    """Ensure every planned scene has exactly one narration passage."""
    expected_scene_ids = {scene.scene_id for scene in production_plan.scenes}
    narrated_scene_ids = [line.scene_id for line in voice_script.lines]

    missing = expected_scene_ids - set(narrated_scene_ids)
    if missing:
        raise ContractViolationError(f"Voice script is missing narration for scene(s): {sorted(missing)}")

    extra = set(narrated_scene_ids) - expected_scene_ids
    if extra:
        raise ContractViolationError(f"Voice script narrates unknown scene(s): {sorted(extra)}")

    if len(narrated_scene_ids) != len(set(narrated_scene_ids)):
        raise ContractViolationError("Voice script has duplicate narration for the same scene")

    if any(not line.narration_text.strip() for line in voice_script.lines):
        raise ContractViolationError("Voice script contains an empty narration passage")

    return voice_script

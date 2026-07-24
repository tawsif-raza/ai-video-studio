from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.voice_script.contract import VoiceScript, VoiceScriptInput
from agents.voice_script.prompt import build_voice_script_prompt
from agents.voice_script.schema import VoiceScriptSchema
from agents.voice_script.validator import validate_voice_script


class VoiceScriptAgent(BaseAgent):
    """Writes the full narration script from a finished ProductionPlan + Storyboard."""

    agent_name = "voice_script"
    output_schema = VoiceScriptSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[VoiceScriptInput] = None

    def build_prompt(self, input_data: VoiceScriptInput) -> str:
        self._current_input = input_data
        return build_voice_script_prompt(input_data)

    def validate_contract(self, validated: VoiceScriptSchema) -> VoiceScriptSchema:
        return validate_voice_script(validated, self._current_input.production_plan)

    def to_contract(self, validated: VoiceScriptSchema) -> VoiceScript:
        source_plan_id = self._current_input.production_plan.plan_id if self._current_input else ""
        return VoiceScript(**validated.model_dump(), source_plan_id=source_plan_id)

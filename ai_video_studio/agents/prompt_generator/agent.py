from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.prompt_generator.contract import PromptGeneratorInput, ShotPrompt
from agents.prompt_generator.prompt import build_prompt_generator_prompt
from agents.prompt_generator.schema import ShotPromptSchema
from agents.prompt_generator.validator import validate_shot_prompt


class PromptGeneratorAgent(BaseAgent):
    """
    Fifth node in the pipeline, run once per shot: (Shot + CharacterProfiles +
    EnvironmentProfile) -> Prompt Generator -> ShotPrompt.

    Constructed with GPTClient rather than GeminiClient - BaseAgent doesn't care,
    it only ever calls self.llm.generate().
    """

    agent_name = "prompt_generator"
    output_schema = ShotPromptSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[PromptGeneratorInput] = None

    def build_prompt(self, input_data: PromptGeneratorInput) -> str:
        self._current_input = input_data
        return build_prompt_generator_prompt(input_data)

    def validate_contract(self, validated: ShotPromptSchema) -> ShotPromptSchema:
        return validate_shot_prompt(validated)

    def to_contract(self, validated: ShotPromptSchema) -> ShotPrompt:
        inp = self._current_input
        return ShotPrompt(
            image_prompt=validated.image_prompt,
            video_motion_prompt=validated.video_motion_prompt,
            scene_id=inp.scene_id,
            shot_id=inp.shot_id,
            duration_seconds=inp.duration_seconds,
        )

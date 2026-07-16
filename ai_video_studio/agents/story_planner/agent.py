from typing import Optional
from agents.base.base_agent import BaseAgent
from agents.story_planner.contract import ProductionPlan, StoryPlannerInput
from agents.story_planner.prompt import build_story_planner_prompt
from agents.story_planner.schema import StoryPlanSchema
from agents.story_planner.validator import validate_story_plan


class StoryPlannerAgent(BaseAgent):
    agent_name = "story_planner"
    output_schema = StoryPlanSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[StoryPlannerInput] = None

    def build_prompt(self, input_data: StoryPlannerInput) -> str:
        self._current_input = input_data
        return build_story_planner_prompt(input_data)

    def validate_contract(self, validated: StoryPlanSchema) -> StoryPlanSchema:
        target = self._current_input.target_duration_seconds if self._current_input else validated.target_duration_seconds
        return validate_story_plan(validated, target_duration=target)

    def to_contract(self, validated: StoryPlanSchema) -> ProductionPlan:
        source_idea = self._current_input.story_idea if self._current_input else ""
        return ProductionPlan(**validated.model_dump(), source_idea=source_idea)
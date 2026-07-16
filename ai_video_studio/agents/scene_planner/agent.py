from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.scene_planner.contract import ScenePlannerInput, Storyboard
from agents.scene_planner.prompt import build_scene_planner_prompt
from agents.scene_planner.schema import ScenePlannerSchema
from agents.scene_planner.validator import validate_scene_plan


class ScenePlannerAgent(BaseAgent):
    """Second node in the pipeline: ProductionPlan -> Scene Planner -> Storyboard."""

    agent_name = "scene_planner"
    output_schema = ScenePlannerSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[ScenePlannerInput] = None

    def build_prompt(self, input_data: ScenePlannerInput) -> str:
        self._current_input = input_data
        return build_scene_planner_prompt(input_data)

    def validate_contract(self, validated: ScenePlannerSchema) -> ScenePlannerSchema:
        production_plan = self._current_input.production_plan
        return validate_scene_plan(validated, production_plan=production_plan)

    def to_contract(self, validated: ScenePlannerSchema) -> Storyboard:
        source_plan_id = self._current_input.production_plan.plan_id if self._current_input else ""
        return Storyboard(**validated.model_dump(), source_plan_id=source_plan_id)

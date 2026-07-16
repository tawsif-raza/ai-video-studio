from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.environment_planner.contract import EnvironmentPlannerInput, EnvironmentSheet
from agents.environment_planner.prompt import build_environment_planner_prompt
from agents.environment_planner.schema import EnvironmentPlannerSchema
from agents.environment_planner.validator import validate_environment_sheet


class EnvironmentPlannerAgent(BaseAgent):
    """
    Fourth node in the pipeline: ProductionPlan -> Environment Planner -> EnvironmentSheet.
    Produces one visual reference per unique location, deduped across repeated scenes.
    """

    agent_name = "environment_planner"
    output_schema = EnvironmentPlannerSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[EnvironmentPlannerInput] = None

    def build_prompt(self, input_data: EnvironmentPlannerInput) -> str:
        self._current_input = input_data
        return build_environment_planner_prompt(input_data)

    def validate_contract(self, validated: EnvironmentPlannerSchema) -> EnvironmentPlannerSchema:
        production_plan = self._current_input.production_plan
        return validate_environment_sheet(validated, production_plan=production_plan)

    def to_contract(self, validated: EnvironmentPlannerSchema) -> EnvironmentSheet:
        source_plan_id = self._current_input.production_plan.plan_id if self._current_input else ""
        return EnvironmentSheet(**validated.model_dump(), source_plan_id=source_plan_id)

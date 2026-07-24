from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.shot_planner.contract import ShotPlan, ShotPlannerInput
from agents.shot_planner.prompt import build_shot_planner_prompt
from agents.shot_planner.schema import ShotPlannerSchema
from agents.shot_planner.validator import validate_shot_plan


class ShotPlannerAgent(BaseAgent):
    """Storyboard -> Shot Planner -> ShotPlan. Confirms/refines per-shot narrative
    beats independent of camera treatment (ARCHITECTURE.md SS12) - Camera Planner
    assigns camera language afterward as its own agent."""

    agent_name = "shot_planner"
    output_schema = ShotPlannerSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[ShotPlannerInput] = None

    def build_prompt(self, input_data: ShotPlannerInput) -> str:
        self._current_input = input_data
        return build_shot_planner_prompt(input_data)

    def validate_contract(self, validated: ShotPlannerSchema) -> ShotPlannerSchema:
        storyboard = self._current_input.storyboard
        return validate_shot_plan(validated, storyboard=storyboard)

    def to_contract(self, validated: ShotPlannerSchema) -> ShotPlan:
        source_storyboard_id = self._current_input.storyboard.storyboard_id if self._current_input else ""
        return ShotPlan(**validated.model_dump(), source_storyboard_id=source_storyboard_id)

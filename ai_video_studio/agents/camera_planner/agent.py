from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.camera_planner.contract import CameraPlan, CameraPlannerInput
from agents.camera_planner.prompt import build_camera_planner_prompt
from agents.camera_planner.schema import CameraPlannerSchema
from agents.camera_planner.validator import validate_camera_plan


class CameraPlannerAgent(BaseAgent):
    """ShotPlan -> Camera Planner -> CameraPlan. Assigns camera angle and movement
    per shot (ARCHITECTURE.md SS12) - narrative content and duration are Shot
    Planner's responsibility and are never touched here."""

    agent_name = "camera_planner"
    output_schema = CameraPlannerSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[CameraPlannerInput] = None

    def build_prompt(self, input_data: CameraPlannerInput) -> str:
        self._current_input = input_data
        return build_camera_planner_prompt(input_data)

    def validate_contract(self, validated: CameraPlannerSchema) -> CameraPlannerSchema:
        shot_plan = self._current_input.shot_plan
        return validate_camera_plan(validated, shot_plan=shot_plan)

    def to_contract(self, validated: CameraPlannerSchema) -> CameraPlan:
        source_shot_plan_id = self._current_input.shot_plan.shot_plan_id if self._current_input else ""
        return CameraPlan(**validated.model_dump(), source_shot_plan_id=source_shot_plan_id)

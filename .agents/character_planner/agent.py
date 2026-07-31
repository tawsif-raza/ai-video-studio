from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.character_planner.contract import CharacterPlannerInput, CharacterSheet
from agents.character_planner.prompt import build_character_planner_prompt
from agents.character_planner.schema import CharacterPlannerSchema
from agents.character_planner.validator import validate_character_sheet


class CharacterPlannerAgent(BaseAgent):
    """
    Third node in the pipeline: ProductionPlan -> Character Planner -> CharacterSheet.
    Produces a visual reference sheet per character for downstream image/video generation.
    """

    agent_name = "character_planner"

    
    output_schema = CharacterPlannerSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[CharacterPlannerInput] = None

    def build_prompt(self, input_data: CharacterPlannerInput) -> str:
        self._current_input = input_data
        return build_character_planner_prompt(input_data)

    def validate_contract(self, validated: CharacterPlannerSchema) -> CharacterPlannerSchema:
        production_plan = self._current_input.production_plan
        return validate_character_sheet(validated, production_plan=production_plan)

    def to_contract(self, validated: CharacterPlannerSchema) -> CharacterSheet:
        source_plan_id = self._current_input.production_plan.plan_id if self._current_input else ""
        return CharacterSheet(**validated.model_dump(), source_plan_id=source_plan_id)


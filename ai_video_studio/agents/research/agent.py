from typing import Optional
from agents.base.base_agent import BaseAgent
from agents.research.contract import ResearchBrief, ResearchInput
from agents.research.prompt import build_research_prompt
from agents.research.schema import ResearchSchema
from agents.research.validator import validate_research_brief


class ResearchAgent(BaseAgent):
    agent_name = "research"
    output_schema = ResearchSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[ResearchInput] = None

    def build_prompt(self, input_data: ResearchInput) -> str:
        self._current_input = input_data
        return build_research_prompt(input_data)

    def validate_contract(self, validated: ResearchSchema) -> ResearchSchema:
        return validate_research_brief(validated)

    def to_contract(self, validated: ResearchSchema) -> ResearchBrief:
        source_idea = self._current_input.story_idea if self._current_input else ""
        return ResearchBrief(**validated.model_dump(), source_idea=source_idea)

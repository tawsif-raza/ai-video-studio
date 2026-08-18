from typing import Optional

from agents.base.base_agent import BaseAgent
from agents.story_planner.contract import ProductionPlan, StoryPlannerInput
from agents.story_planner.prompt import build_story_planner_prompt
from agents.story_planner.schema import StoryPlanSchema
from agents.story_planner.validator import SceneCountMismatchError, validate_story_plan
from config import settings
from models import AgentResult
from utils.logger import get_logger

logger = get_logger(__name__)


class StoryPlannerAgent(BaseAgent):
    agent_name = "story_planner"
    output_schema = StoryPlanSchema

    def __init__(self, llm_client):
        super().__init__(llm_client)
        self._current_input: Optional[StoryPlannerInput] = None
        self._retry_note: str = ""
        self._last_error_was_scene_count_mismatch = False

    def build_prompt(self, input_data: StoryPlannerInput) -> str:
        self._current_input = input_data
        return build_story_planner_prompt(input_data, correction_note=self._retry_note)

    def validate_contract(self, validated: StoryPlanSchema) -> StoryPlanSchema:
        target = self._current_input.target_duration_seconds if self._current_input else validated.target_duration_seconds
        mode = self._current_input.scene_count_mode if self._current_input else "default"
        scene_count = self._current_input.scene_count if self._current_input else None
        self._last_error_was_scene_count_mismatch = False
        try:
            return validate_story_plan(
                validated, target_duration=target, scene_count_mode=mode, scene_count=scene_count
            )
        except SceneCountMismatchError:
            self._last_error_was_scene_count_mismatch = True
            raise

    def to_contract(self, validated: StoryPlanSchema) -> ProductionPlan:
        source_idea = self._current_input.story_idea if self._current_input else ""
        mode = self._current_input.scene_count_mode if self._current_input else "default"
        scene_count = self._current_input.scene_count if self._current_input else None
        return ProductionPlan(
            **validated.model_dump(),
            source_idea=source_idea,
            scene_count_mode=mode,
            scene_count=scene_count,
        )

    def run(self, input_data: StoryPlannerInput) -> AgentResult:
        """Custom scene counts get a bounded number of self-correcting
        retries on top of BaseAgent's own schema-validation retries
        (agents/base/base_agent.py's @retry only covers LLMCallError/
        SchemaValidationError, not the business-rule ContractViolationError
        validate_contract raises after that inner loop has already
        returned) - without this, a single wrong scene count would fail
        the whole run instead of giving the model a chance to correct
        itself, per the "controlled correction/retry, not silent
        acceptance" requirement for the Custom Scene Count override.

        Only a scene-count mismatch is retried here; every other
        ContractViolationError (duplicate ids, duration tolerance, unknown
        character) still fails immediately on the first attempt, exactly
        as it always has."""
        if input_data.scene_count_mode != "custom":
            self._retry_note = ""
            return super().run(input_data)

        max_attempts = max(1, settings.MAX_RETRIES)
        result: Optional[AgentResult] = None
        for attempt in range(1, max_attempts + 1):
            self._last_error_was_scene_count_mismatch = False
            result = super().run(input_data)

            if result.success or not self._last_error_was_scene_count_mismatch:
                self._retry_note = ""
                return result

            logger.warning(
                f"[story_planner] scene count mismatch on attempt {attempt}/{max_attempts}: {result.error}"
            )
            self._retry_note = (
                f"\nCORRECTION NEEDED: your previous attempt did not produce exactly "
                f"{input_data.scene_count} scenes ({result.error}). Recount and return "
                f"EXACTLY {input_data.scene_count} scenes this time - this is a hard "
                f"requirement, not a suggestion.\n"
            )

        self._retry_note = ""
        return result

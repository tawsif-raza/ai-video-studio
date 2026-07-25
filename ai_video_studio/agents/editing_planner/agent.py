from datetime import UTC, datetime

from agents.editing_planner.contract import EditingPlannerInput
from agents.editing_planner.validator import build_editing_plan
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.editing_planner")


class EditingPlannerAgent:
    """
    Editing Planning is deterministic, like the rest of Producer Studio's
    stages so far: it merges Timeline, SubtitlePlan, and MusicPlan into one
    blueprint and calls no LLM (ARCHITECTURE.md SS6). It deliberately does
    not extend BaseAgent and has no prompt.py or schema.py, for the same
    reason as Asset Validation, Timeline Planning, Subtitle Planning, and
    Music Planning; validator.py carries the actual merge/transition logic.
    It still exposes the same run(input_data) -> AgentResult interface so
    ProducerStudioController sequences it identically to the stages before
    it.
    """

    agent_name = "editing_planner"

    def run(self, input_data: EditingPlannerInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            editing_plan = build_editing_plan(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed - {len(editing_plan.segments)} segments")
            return AgentResult(success=True, data=editing_plan, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

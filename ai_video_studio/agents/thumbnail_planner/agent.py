from datetime import UTC, datetime

from agents.thumbnail_planner.contract import ThumbnailPlannerInput
from agents.thumbnail_planner.validator import build_thumbnail_plan
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.thumbnail_planner")


class ThumbnailPlannerAgent:
    """
    Thumbnail Planning is deterministic, like every Producer Studio stage
    before it: it composes a thumbnail strategy and generation prompt from
    the editing plan's hero shot, the story, and the Character Bible's
    already-paste-ready reference_prompt, and calls no LLM (ARCHITECTURE.md
    SS6). It deliberately does not extend BaseAgent and has no prompt.py or
    schema.py, for the same reason as Asset Validation, Timeline, Subtitle,
    Music, and Editing Planning; validator.py carries the actual
    composition logic. It still exposes the same
    run(input_data) -> AgentResult interface so ProducerStudioController
    sequences it identically to the stages before it.
    """

    agent_name = "thumbnail_planner"

    def run(self, input_data: ThumbnailPlannerInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            thumbnail_plan = build_thumbnail_plan(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed - {len(thumbnail_plan.variants)} variant(s)")
            return AgentResult(success=True, data=thumbnail_plan, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

from datetime import UTC, datetime

from agents.publishing_planner.contract import PublishingPlannerInput
from agents.publishing_planner.validator import build_publishing_plan
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.publishing_planner")


class PublishingPlannerAgent:
    """
    Publishing Metadata is deterministic, like every Producer Studio stage
    before it: it composes canonical + YouTube-specific metadata from the
    story and Project Metadata, and calls no LLM and no publishing API
    (ARCHITECTURE.md SS6). It deliberately does not extend BaseAgent and has
    no prompt.py or schema.py, for the same reason as the five planning
    stages before it; validator.py carries the actual composition logic. It
    still exposes the same run(input_data) -> AgentResult interface so
    ProducerStudioController sequences it identically - it is the sixth and
    last planning sub-stage, after which the project reaches EDIT_PLAN_READY.
    """

    agent_name = "publishing_planner"

    def run(self, input_data: PublishingPlannerInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            publishing_plan = build_publishing_plan(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed - category={publishing_plan.canonical.category}")
            return AgentResult(success=True, data=publishing_plan, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

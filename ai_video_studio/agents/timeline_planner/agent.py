from datetime import UTC, datetime

from agents.timeline_planner.contract import TimelinePlannerInput
from agents.timeline_planner.validator import build_timeline
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.timeline_planner")


class TimelinePlannerAgent:
    """
    Timeline Planning is deterministic, like Asset Validation: it sequences
    already-approved media against already-planned durations and calls no LLM
    (ARCHITECTURE.md SS6). It deliberately does not extend BaseAgent - there is
    no prompt to build and no raw LLM output shape to validate - and has no
    prompt.py or schema.py for the same reason; validator.py carries the
    actual sequencing/timing logic. It still exposes the same
    run(input_data) -> AgentResult interface as every other agent, so
    ProducerStudioController sequences it identically to Asset Validation and
    to Director Studio's stages.
    """

    agent_name = "timeline_planner"

    def run(self, input_data: TimelinePlannerInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            timeline = build_timeline(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(
                f"[{self.agent_name}] Completed - {len(timeline.clips)} clips, "
                f"{timeline.total_duration_seconds}s total"
            )
            return AgentResult(success=True, data=timeline, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

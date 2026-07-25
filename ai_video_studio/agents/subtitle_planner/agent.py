from datetime import UTC, datetime

from agents.subtitle_planner.contract import SubtitlePlannerInput
from agents.subtitle_planner.validator import build_subtitle_plan
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.subtitle_planner")


class SubtitlePlannerAgent:
    """
    Subtitle Planning is deterministic, like Asset Validation and Timeline
    Planning: it segments already-written narration text and times it against
    Timeline's already-computed voice_segments, and calls no LLM
    (ARCHITECTURE.md SS6). It deliberately does not extend BaseAgent and has
    no prompt.py or schema.py, for the same reason as the other two Producer
    Studio agents; validator.py carries the actual segmentation/timing logic.
    It still exposes the same run(input_data) -> AgentResult interface so
    ProducerStudioController sequences it identically to the stages before it.
    """

    agent_name = "subtitle_planner"

    def run(self, input_data: SubtitlePlannerInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            subtitle_plan = build_subtitle_plan(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed - {len(subtitle_plan.cues)} cues")
            return AgentResult(success=True, data=subtitle_plan, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

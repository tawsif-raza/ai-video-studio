from datetime import UTC, datetime

from agents.music_planner.contract import MusicPlannerInput
from agents.music_planner.validator import build_music_plan
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.music_planner")


class MusicPlannerAgent:
    """
    Music Planning is deterministic, like the rest of Producer Studio's
    stages so far: it derives a per-scene music strategy from Timeline's
    already-computed scene windows, Production Package moods, and
    SubtitlePlan's narration timing, and calls no LLM (ARCHITECTURE.md SS6).
    It deliberately does not extend BaseAgent and has no prompt.py or
    schema.py, for the same reason as Asset Validation, Timeline Planning,
    and Subtitle Planning; validator.py carries the actual
    classification/timing logic. It still exposes the same
    run(input_data) -> AgentResult interface so ProducerStudioController
    sequences it identically to the stages before it.
    """

    agent_name = "music_planner"

    def run(self, input_data: MusicPlannerInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            music_plan = build_music_plan(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed - {len(music_plan.cues)} cues")
            return AgentResult(success=True, data=music_plan, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

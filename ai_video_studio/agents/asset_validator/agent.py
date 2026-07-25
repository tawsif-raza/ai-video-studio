from datetime import UTC, datetime

from agents.asset_validator.contract import AssetValidatorInput
from agents.asset_validator.validator import validate_assets
from models import AgentMetadata, AgentResult
from utils.logger import get_logger

logger = get_logger("agents.asset_validator")


class AssetValidatorAgent:
    """
    Asset Validation is deterministic: it checks that imported media covers what
    the Production Package expects, and calls no LLM (ARCHITECTURE.md SS6). It
    deliberately does not extend BaseAgent, which is built around the LLM
    generate/retry/parse cycle every other agent needs - there is no prompt to
    build and no raw LLM output shape to validate here, so this agent has no
    prompt.py or schema.py either; validator.py carries the actual logic instead
    of business rules layered on top of an LLM's JSON. It still exposes the same
    run(input_data) -> AgentResult interface as every LLM-backed agent, so
    ProducerStudioController sequences it identically to Director Studio's stages.
    """

    agent_name = "asset_validator"

    def run(self, input_data: AssetValidatorInput) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=None)
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            manifest = validate_assets(input_data)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed - is_valid={manifest.is_valid}")
            return AgentResult(success=True, data=manifest, metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed unexpectedly")
            return AgentResult(success=False, error=str(e), metadata=meta)

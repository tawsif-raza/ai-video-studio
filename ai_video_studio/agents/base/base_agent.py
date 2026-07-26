from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Type

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agents.base.exceptions import LLMCallError, SchemaValidationError, ContractViolationError
from models import AgentResult, AgentMetadata
from utils.json_utils import extract_json
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    agent_name: str = "base_agent"
    output_schema: Type[BaseModel] = None

    def __init__(self, llm_client):
        if self.output_schema is None:
            raise NotImplementedError(f"{self.__class__.__name__} must set output_schema")
        self.llm = llm_client

    @abstractmethod
    def build_prompt(self, input_data: Any) -> str:
        ...

    def validate_contract(self, validated: BaseModel) -> BaseModel:
        return validated  # override for business rules

    def to_contract(self, validated: BaseModel) -> BaseModel:
        return validated  # override to map to a richer public output type

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((LLMCallError, SchemaValidationError)),
        reraise=True,
    )
    def _call_and_validate(self, prompt: str) -> BaseModel:
        raw_text = self.llm.generate(prompt)
        if not raw_text:
            raise LLMCallError(f"[{self.agent_name}] Empty response from LLM")
        try:
            data = extract_json(raw_text)
        except ValueError as e:
            raise SchemaValidationError(f"[{self.agent_name}] Could not extract JSON: {e}")
        try:
            return self.output_schema(**data)
        except Exception as e:
            raise SchemaValidationError(f"[{self.agent_name}] Schema validation failed: {e}")

    def run(self, input_data: Any) -> AgentResult:
        meta = AgentMetadata(agent_name=self.agent_name, model_used=getattr(self.llm, "model_name", None))
        logger.info(f"[{self.agent_name}] Starting run")
        try:
            prompt = self.build_prompt(input_data)
            validated = self._call_and_validate(prompt)
            validated = self.validate_contract(validated)
            contract_output = self.to_contract(validated)
            meta.finished_at = datetime.now(UTC)
            logger.info(f"[{self.agent_name}] Completed successfully")
            return AgentResult(success=True, data=contract_output, metadata=meta)
        except ContractViolationError as e:
            meta.finished_at = datetime.now(UTC)
            logger.error(f"[{self.agent_name}] Contract violation: {e}")
            return AgentResult(success=False, error=str(e), metadata=meta)
        except Exception as e:
            meta.finished_at = datetime.now(UTC)
            logger.exception(f"[{self.agent_name}] Failed after retries")
            return AgentResult(success=False, error=str(e), metadata=meta)

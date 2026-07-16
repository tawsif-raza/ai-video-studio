from datetime import UTC, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    agent_name: str
    version: str = "1.0"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: Optional[datetime] = None
    model_used: Optional[str] = None


class AgentResult(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: AgentMetadata
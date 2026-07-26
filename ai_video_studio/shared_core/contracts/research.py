import uuid
from datetime import UTC, datetime
from typing import List

from pydantic import BaseModel, Field


class ResearchSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    key_facts: List[str]
    considerations: List[str]


class ResearchBrief(ResearchSchema):
    brief_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_idea: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

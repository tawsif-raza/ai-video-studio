import uuid
from datetime import UTC, datetime
from typing import List

from pydantic import BaseModel, Field


class NarrationLine(BaseModel):
    scene_id: int
    narration_text: str


class VoiceScriptSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    lines: List[NarrationLine]


class VoiceScript(VoiceScriptSchema):
    """Public output contract for Project Manager's Production Package export."""

    script_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

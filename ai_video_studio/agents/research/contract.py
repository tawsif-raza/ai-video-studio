from typing import Optional
from pydantic import BaseModel

from shared_core.contracts.research import ResearchBrief

__all__ = ["ResearchBrief", "ResearchInput"]


class ResearchInput(BaseModel):
    story_idea: str
    tone: Optional[str] = None
    audience: Optional[str] = None

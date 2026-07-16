import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from agents.story_planner.schema import StoryPlanSchema


class StoryPlannerInput(BaseModel):
    story_idea: str
    target_duration_seconds: int = 60
    tone: Optional[str] = None
    audience: Optional[str] = None


class ProductionPlan(StoryPlanSchema):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_idea: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
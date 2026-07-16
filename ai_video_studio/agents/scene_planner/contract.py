import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from agents.scene_planner.schema import ScenePlannerSchema
from agents.story_planner.contract import ProductionPlan


class ScenePlannerInput(BaseModel):
    """Typed input received from the Story Planner."""

    production_plan: ProductionPlan


class Storyboard(ScenePlannerSchema):
    """Public output contract for downstream agents."""

    storyboard_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)

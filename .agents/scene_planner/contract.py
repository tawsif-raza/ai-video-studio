import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from agents.scene_planner.schema import ScenePlannerSchema
from agents.story_planner.contract import ProductionPlan


class ScenePlannerInput(BaseModel):
    """
    Note this isn't a string prompt — it's the actual ProductionPlan object the
    Story Planner produced. That's the whole point of typed contracts: Scene
    Planner doesn't re-parse text, it consumes structured data directly.
    """

    production_plan: ProductionPlan


class Storyboard(ScenePlannerSchema):
    """Public output contract — what Character/Environment/Prompt agents consume next."""

    storyboard_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
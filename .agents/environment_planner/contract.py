import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from agents.environment_planner.schema import EnvironmentPlannerSchema
from agents.story_planner.contract import ProductionPlan


def get_unique_settings(production_plan: ProductionPlan) -> List[str]:
    """
    Environments repeat across scenes (the same rooftop can appear in 3 scenes),
    so we dedupe by exact setting string before asking for profiles — one profile
    per real location, not one per scene. Order preserved by first appearance.
    """
    seen: List[str] = []
    for scene in production_plan.scenes:
        if scene.setting not in seen:
            seen.append(scene.setting)
    return seen


class EnvironmentPlannerInput(BaseModel):
    production_plan: ProductionPlan
    art_style: Optional[str] = Field(
        None, description="Should match the art_style passed to Character Planner for visual consistency"
    )


class EnvironmentSheet(EnvironmentPlannerSchema):
    """Public output contract — what Image/Video Generation consume next."""

    sheet_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
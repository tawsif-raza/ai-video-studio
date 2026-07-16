import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from agents.character_planner.schema import CharacterPlannerSchema
from agents.story_planner.contract import ProductionPlan


class CharacterPlannerInput(BaseModel):
    production_plan: ProductionPlan
    art_style: Optional[str] = Field(
        None, description="Global style guide, e.g. '3D animated, Pixar-style, warm cinematic lighting'"
    )


class CharacterSheet(CharacterPlannerSchema):
    """Public output contract — what Image Generation and Prompt Generator consume next."""

    sheet_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
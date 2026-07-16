import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from agents.character_planner.schema import CharacterPlannerSchema
from agents.story_planner.contract import ProductionPlan


class CharacterPlannerInput(BaseModel):
    production_plan: ProductionPlan
    art_style: Optional[str] = Field(
        None, description="Global visual style guide shared by all characters"
    )


class CharacterSheet(CharacterPlannerSchema):
    """Public output contract for downstream image and prompt generation."""

    sheet_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)

from typing import Optional

from pydantic import BaseModel, Field

from shared_core.contracts.character_sheet import CharacterSheet
from shared_core.contracts.production_plan import ProductionPlan

__all__ = ["CharacterPlannerInput", "CharacterSheet", "ProductionPlan"]


class CharacterPlannerInput(BaseModel):
    production_plan: ProductionPlan
    art_style: Optional[str] = Field(
        None, description="Global visual style guide shared by all characters"
    )

from typing import List, Optional

from pydantic import BaseModel, Field

from shared_core.contracts.environment_sheet import EnvironmentSheet
from shared_core.contracts.production_plan import ProductionPlan

__all__ = ["EnvironmentPlannerInput", "EnvironmentSheet", "ProductionPlan", "get_unique_settings"]


def get_unique_settings(production_plan: ProductionPlan) -> List[str]:
    """
    Environments repeat across scenes (the same rooftop can appear in 3 scenes),
    so we dedupe by exact setting string before asking for profiles - one profile
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

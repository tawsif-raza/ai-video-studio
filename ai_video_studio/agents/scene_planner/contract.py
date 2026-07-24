from pydantic import BaseModel

from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.storyboard import Storyboard

__all__ = ["ProductionPlan", "ScenePlannerInput", "Storyboard"]


class ScenePlannerInput(BaseModel):
    """Typed input received from the Story Planner."""

    production_plan: ProductionPlan

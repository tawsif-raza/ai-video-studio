from pydantic import BaseModel

from shared_core.contracts.shot_plan import ShotPlan
from shared_core.contracts.storyboard import Storyboard

__all__ = ["ShotPlan", "ShotPlannerInput", "Storyboard"]


class ShotPlannerInput(BaseModel):
    """Typed input received from Scene Planner."""

    storyboard: Storyboard

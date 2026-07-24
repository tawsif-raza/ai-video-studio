from pydantic import BaseModel

from shared_core.contracts.camera_plan import CameraPlan
from shared_core.contracts.shot_plan import ShotPlan

__all__ = ["CameraPlan", "CameraPlannerInput", "ShotPlan"]


class CameraPlannerInput(BaseModel):
    """Typed input received from Shot Planner."""

    shot_plan: ShotPlan

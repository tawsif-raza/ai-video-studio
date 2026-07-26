import uuid
from datetime import UTC, datetime
from typing import List

from pydantic import BaseModel, Field


class CameraShot(BaseModel):
    """Camera treatment only (ARCHITECTURE.md SS12) - narrative content, characters,
    and duration are Shot Planner's responsibility and are never repeated here."""

    shot_id: int
    camera_angle: str = Field(..., description="e.g. wide shot, medium shot, close-up")
    camera_movement: str = Field(..., description="e.g. static, slow pan left, zoom in")


class CameraScenePlan(BaseModel):
    scene_id: int
    shots: List[CameraShot]


class CameraPlannerSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    scene_plans: List[CameraScenePlan]


class CameraPlan(CameraPlannerSchema):
    """Public output contract for downstream agents (Prompt Intelligence)."""

    camera_plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_shot_plan_id: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

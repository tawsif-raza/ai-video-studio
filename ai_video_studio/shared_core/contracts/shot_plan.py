import uuid
from datetime import UTC, datetime
from typing import List

from pydantic import BaseModel, Field


class ShotItem(BaseModel):
    """Shot structure and sequence only (ARCHITECTURE.md SS12) - no camera fields.
    Camera Planner assigns camera treatment afterward, keyed off shot_id."""

    shot_id: int
    description: str = Field(..., description="What happens visually in this specific shot")
    characters_in_shot: List[str]
    duration_seconds: int = Field(..., ge=1, le=15)


class ShotScenePlan(BaseModel):
    scene_id: int
    shots: List[ShotItem]


class ShotPlannerSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    scene_plans: List[ShotScenePlan]


class ShotPlan(ShotPlannerSchema):
    """Public output contract for downstream agents (Camera Planner, Prompt Intelligence)."""

    shot_plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_storyboard_id: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

import uuid
from datetime import UTC, datetime
from typing import List

from pydantic import BaseModel, Field


class ShotBrief(BaseModel):
    """No camera fields here by design (ARCHITECTURE.md SS12): Scene Planner defines
    shot structure only - camera treatment is Camera Planner's sole responsibility,
    assigned later in the pipeline against Shot Planner's output."""

    shot_id: int
    description: str = Field(..., description="What happens visually in this specific shot")
    characters_in_shot: List[str]
    duration_seconds: int = Field(..., ge=1, le=15)


class ScenePlan(BaseModel):
    scene_id: int
    shots: List[ShotBrief]


class ScenePlannerSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    scene_plans: List[ScenePlan]


class Storyboard(ScenePlannerSchema):
    """Public output contract for downstream agents."""

    storyboard_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_plan_id: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

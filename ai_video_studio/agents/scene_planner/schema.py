from typing import List

from pydantic import BaseModel, Field


class ShotBrief(BaseModel):
    shot_id: int
    camera_angle: str = Field(..., description="e.g. wide shot, medium shot, close-up")
    camera_movement: str = Field(..., description="e.g. static, slow pan left, zoom in")
    description: str = Field(..., description="What happens visually in this specific shot")
    characters_in_shot: List[str]
    duration_seconds: int = Field(..., ge=1, le=15)


class ScenePlan(BaseModel):
    scene_id: int
    shots: List[ShotBrief]


class ScenePlannerSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    scene_plans: List[ScenePlan]

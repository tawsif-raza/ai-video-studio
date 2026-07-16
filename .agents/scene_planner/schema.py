from typing import List

from pydantic import BaseModel, Field


class ShotBrief(BaseModel):
    shot_id: int
    camera_angle: str = Field(
        ..., description="e.g. wide shot, medium shot, close-up, over-the-shoulder, aerial"
    )
    camera_movement: str = Field(
        ..., description="e.g. static, slow pan left, zoom in, tracking shot, handheld"
    )
    description: str = Field(..., description="What happens visually in this specific shot")
    characters_in_shot: List[str]
    duration_seconds: int = Field(..., ge=1, le=15)


class ScenePlan(BaseModel):
    scene_id: int
    shots: List[ShotBrief]


class ScenePlannerSchema(BaseModel):
    """Exact shape we require Gemini's JSON output to satisfy."""

    scene_plans: List[ScenePlan]
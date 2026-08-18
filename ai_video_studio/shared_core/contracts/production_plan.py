import uuid
from datetime import UTC, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CharacterBrief(BaseModel):
    name: str
    role: str
    one_line_description: str


class SceneBrief(BaseModel):
    scene_id: int
    title: str
    summary: str
    setting: str
    mood: str
    characters_present: List[str]
    estimated_duration_seconds: int = Field(..., ge=2, le=90)


class StoryPlanSchema(BaseModel):
    title: str
    logline: str
    theme: str
    target_duration_seconds: int
    tone: str
    characters: List[CharacterBrief]
    scenes: List[SceneBrief]


class ProductionPlan(StoryPlanSchema):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_idea: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Custom Scene Count Override (Director Studio New Project UI). Set
    # programmatically by StoryPlannerAgent.to_contract() from the caller's
    # request, never produced by the LLM itself - StoryPlanSchema (the LLM's
    # exact output shape) deliberately does not carry these fields.
    # "default" preserves the existing LLM-judged (~20-21 scene) behavior;
    # "custom" means scene_count is a hard requirement len(scenes) must equal
    # exactly (enforced by agents/story_planner/validator.py).
    scene_count_mode: str = "default"
    scene_count: Optional[int] = None

from typing import List
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
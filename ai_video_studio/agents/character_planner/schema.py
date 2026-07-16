from typing import List

from pydantic import BaseModel, Field


class CharacterVisualProfile(BaseModel):
    name: str = Field(..., description="Must exactly match a Production Plan character name")
    age_range: str
    build: str = Field(..., description="Body type or physique")
    face_details: str = Field(..., description="Face shape, eyes, and notable features")
    hair: str
    outfit: str = Field(..., description="Clothing or costume description")
    color_palette: List[str] = Field(..., min_length=2, max_length=6)
    distinguishing_features: str
    art_style_keywords: List[str]
    reference_prompt: str = Field(..., min_length=30)


class CharacterPlannerSchema(BaseModel):
    """Exact shape required of the LLM JSON output."""

    character_profiles: List[CharacterVisualProfile]

from typing import List

from pydantic import BaseModel, Field


class CharacterVisualProfile(BaseModel):
    name: str = Field(..., description="Must match a character name from the Production Plan exactly")
    age_range: str
    build: str = Field(..., description="Body type / physique")
    face_details: str = Field(..., description="Face shape, eyes, notable facial features")
    hair: str
    outfit: str = Field(..., description="Clothing / costume description")
    color_palette: List[str] = Field(..., min_length=2, max_length=6, description="Dominant colors for this character")
    distinguishing_features: str = Field(..., description="Anything that makes this character instantly recognizable")
    art_style_keywords: List[str] = Field(..., description="e.g. '3D animated', 'Pixar-style', 'soft cinematic lighting'")
    reference_prompt: str = Field(
        ..., min_length=30,
        description="Single consolidated visual description ready to paste directly into an image-generation prompt"
    )


class CharacterPlannerSchema(BaseModel):
    """Exact shape we require the LLM's JSON output to satisfy."""

    character_profiles: List[CharacterVisualProfile]
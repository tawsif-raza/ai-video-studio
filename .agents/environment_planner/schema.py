from typing import List

from pydantic import BaseModel, Field


class EnvironmentProfile(BaseModel):
    setting: str = Field(..., description="Must match a setting string from the Production Plan exactly")
    time_of_day: str
    weather: str
    key_visual_elements: List[str] = Field(..., min_length=1, description="Notable props/background elements")
    color_palette: List[str] = Field(..., min_length=2, max_length=6)
    lighting: str
    atmosphere: str = Field(..., description="The mood this environment itself conveys")
    art_style_keywords: List[str] = Field(..., description="Should match the character sheet's art style")
    reference_prompt: str = Field(
        ..., min_length=30,
        description="Single consolidated description ready to paste directly into an image-generation prompt"
    )


class EnvironmentPlannerSchema(BaseModel):
    """Exact shape we require the LLM's JSON output to satisfy."""

    environment_profiles: List[EnvironmentProfile]

    
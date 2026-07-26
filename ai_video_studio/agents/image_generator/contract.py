import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ImageGenInput(BaseModel):
    scene_id: int
    base_prompt: str = Field(..., description="The scene's representative image_prompt from Prompt Generator")
    aspect_ratio: str = "9:16"


class ImageAsset(BaseModel):
    """Public output - what Video Generation consumes next."""

    asset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scene_id: int
    file_path: str
    prompt_used: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def build_image_prompt(input_data: ImageGenInput) -> str:
    orientation = "vertical portrait" if input_data.aspect_ratio == "9:16" else input_data.aspect_ratio
    return (
        f"{input_data.base_prompt}\n\n"
        f"Composition: {orientation} orientation, aspect ratio {input_data.aspect_ratio}, "
        f"framed for mobile short-form video (Reels/Shorts/TikTok)."
    )

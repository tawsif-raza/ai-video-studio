from pydantic import BaseModel, Field


class ShotPromptSchema(BaseModel):
    """
    Deliberately does NOT include scene_id/shot_id/duration - we already know those
    from Python, so we never ask the LLM to echo identifiers back to us. Trusting an
    LLM to correctly echo IDs is an easy, silent way for shots to get mismatched;
    Python attaches them after validation instead.
    """

    image_prompt: str = Field(..., min_length=40, description="Final, polished prompt for image generation")
    video_motion_prompt: str = Field(
        ..., min_length=15, description="Short description of motion/camera movement for video generation"
    )

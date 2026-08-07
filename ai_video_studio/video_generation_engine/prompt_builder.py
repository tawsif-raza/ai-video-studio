"""
Pure composer of the final, provider-ready video generation prompt string
(ARCHITECTURE.md SS25.6) - the video-generation analogue of
agents/image_generator/contract.py's build_image_prompt, same composition
scope and shape, new function. No filesystem access, no subprocess, no
provider call.

Composes from exactly what VideoGenerationRequest actually carries
(shot_prompt + options) - not from a CameraPlan, which SS25.4 deliberately
does not add as a field: VideoGenerationRequest reuses ShotPrompt only, the
same "only what the engine actually receives" discipline build_image_prompt
already follows for ImageGenInput (which likewise has no CameraPlan field
despite Character/Environment Bibles existing upstream).
"""

from shared_core.contracts.prompt_set import ShotPrompt
from shared_core.contracts.video_generation import VideoGenerationOptions


def build_video_prompt(shot_prompt: ShotPrompt, options: VideoGenerationOptions) -> str:
    orientation = "vertical portrait" if options.aspect_ratio == "9:16" else options.aspect_ratio
    return (
        f"{shot_prompt.video_motion_prompt}\n\n"
        f"Duration: {shot_prompt.duration_seconds}s. "
        f"Composition: {orientation} orientation, aspect ratio {options.aspect_ratio}, "
        f"framed for mobile short-form video (Reels/Shorts/TikTok)."
    )

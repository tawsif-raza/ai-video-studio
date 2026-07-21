from typing import List

from agents.prompt_generator.contract import ShotPrompt


def select_representative_prompt(scene_shots: List[ShotPrompt]) -> str:
    """Business rule: a scene's first shot represents it for image generation."""
    return scene_shots[0].image_prompt

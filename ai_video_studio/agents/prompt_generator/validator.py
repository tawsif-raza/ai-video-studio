from agents.base.exceptions import ContractViolationError
from agents.prompt_generator.schema import ShotPromptSchema


def validate_shot_prompt(shot_prompt: ShotPromptSchema) -> ShotPromptSchema:
    """
    The one thing schema validation can't catch: a lazy response that just repeats
    image_prompt as video_motion_prompt instead of actually describing motion.
    """
    if shot_prompt.image_prompt.strip() == shot_prompt.video_motion_prompt.strip():
        raise ContractViolationError(
            "video_motion_prompt is identical to image_prompt - motion was not actually described"
        )
    return shot_prompt

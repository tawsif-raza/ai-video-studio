import pytest

from agents.base.exceptions import ContractViolationError
from agents.prompt_generator.schema import ShotPromptSchema
from agents.prompt_generator.validator import validate_shot_prompt


def test_valid_shot_prompt_passes():
    prompt = ShotPromptSchema(
        image_prompt="A lean young woman with black hair stands in a misty forest clearing at dawn, "
                      "warm morning light filtering through tall trees.",
        video_motion_prompt="She slowly turns her head toward the light as the camera pans right.",
    )
    validate_shot_prompt(prompt)


def test_identical_prompts_rejected():
    same_text = "A lean young woman stands in a misty forest clearing at dawn under tall trees."
    prompt = ShotPromptSchema(image_prompt=same_text, video_motion_prompt=same_text)
    with pytest.raises(ContractViolationError):
        validate_shot_prompt(prompt)

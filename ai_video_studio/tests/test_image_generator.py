import pytest
from pathlib import Path

from agents.base.exceptions import ContractViolationError
from agents.image_generator.contract import ImageGenInput, build_image_prompt
from agents.image_generator.validator import validate_image_file


def test_build_image_prompt_includes_aspect_ratio():
    input_data = ImageGenInput(scene_id=1, base_prompt="A robot at a party.", aspect_ratio="9:16")
    prompt = build_image_prompt(input_data)
    assert "9:16" in prompt
    assert "A robot at a party." in prompt
    assert "vertical portrait" in prompt


def test_validate_image_file_missing_rejected(tmp_path):
    fake_path = tmp_path / "does_not_exist.png"
    with pytest.raises(ContractViolationError):
        validate_image_file(fake_path)


def test_validate_image_file_too_small_rejected(tmp_path):
    tiny_file = tmp_path / "tiny.png"
    tiny_file.write_bytes(b"not a real image")
    with pytest.raises(ContractViolationError):
        validate_image_file(tiny_file)


def test_validate_image_file_valid_size_passes(tmp_path):
    real_looking_file = tmp_path / "scene_1.png"
    real_looking_file.write_bytes(b"0" * 10_000)
    result = validate_image_file(real_looking_file)
    assert result == real_looking_file
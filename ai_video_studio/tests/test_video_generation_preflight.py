import pytest

from shared_core.contracts.prompt_set import ShotPrompt
from shared_core.contracts.video_generation import VideoGenerationOptions, VideoGenerationRequest
from video_generation_engine.errors import MediaAccessError
from video_generation_engine.preflight import verify_generation_inputs


def _request(output_dir, **option_overrides):
    shot_prompt = ShotPrompt(
        scene_id=1, shot_id=1, duration_seconds=5,
        image_prompt="x" * 50, video_motion_prompt="camera pans across the scene slowly",
    )
    return VideoGenerationRequest(
        shot_prompt=shot_prompt, scene_id=1, shot_id=1, output_dir=str(output_dir),
        options=VideoGenerationOptions(**option_overrides),
    )


def test_passes_when_output_dir_is_writable_and_no_seed_image(tmp_path):
    verify_generation_inputs(_request(tmp_path / "video"))  # should not raise


def test_creates_output_dir_if_absent(tmp_path):
    target = tmp_path / "nested" / "video"
    verify_generation_inputs(_request(target))
    assert target.is_dir()


def test_raises_when_seed_image_missing(tmp_path):
    missing_seed = tmp_path / "seed.png"
    with pytest.raises(MediaAccessError) as exc:
        verify_generation_inputs(_request(tmp_path / "video", seed_image_path=str(missing_seed)))
    assert "seed.png" in str(exc.value)


def test_passes_when_seed_image_present(tmp_path):
    seed = tmp_path / "seed.png"
    seed.write_bytes(b"x")
    verify_generation_inputs(_request(tmp_path / "video", seed_image_path=str(seed)))  # should not raise

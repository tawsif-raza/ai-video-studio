import pytest

from shared_core.contracts.prompt_set import PromptSet, ShotPrompt
from shared_core.contracts.video_generation import ShotMediaSelection, VideoGenerationOptions
from video_generation_engine.errors import VideoGenerationInputError
from video_generation_engine.request_builder import (
    build_generation_request,
    resolve_selected_shots,
    validate_generation_request,
)


def _shot_prompt(scene_id, shot_id, **overrides):
    defaults = dict(
        scene_id=scene_id, shot_id=shot_id, duration_seconds=5,
        image_prompt="x" * 50, video_motion_prompt="camera pans across the scene slowly",
    )
    defaults.update(overrides)
    return ShotPrompt(**defaults)


def _prompt_set():
    return PromptSet(shots=[_shot_prompt(1, 1), _shot_prompt(1, 2), _shot_prompt(2, 1)])


# ---- resolve_selected_shots ----

def test_resolve_selected_shots_returns_only_video_mode_matches():
    selections = [
        ShotMediaSelection(scene_id=1, shot_id=1, mode="video"),
        ShotMediaSelection(scene_id=1, shot_id=2, mode="image"),
    ]
    resolved = resolve_selected_shots(_prompt_set(), selections)
    assert len(resolved) == 1
    assert (resolved[0].scene_id, resolved[0].shot_id) == (1, 1)


def test_resolve_selected_shots_returns_empty_for_no_video_selections():
    selections = [ShotMediaSelection(scene_id=1, shot_id=1, mode="image")]
    assert resolve_selected_shots(_prompt_set(), selections) == []


def test_resolve_selected_shots_raises_for_unknown_shot():
    selections = [ShotMediaSelection(scene_id=9, shot_id=9, mode="video")]
    with pytest.raises(VideoGenerationInputError) as exc:
        resolve_selected_shots(_prompt_set(), selections)
    assert "scene 9 shot 9" in str(exc.value)


def test_resolve_selected_shots_names_every_missing_shot_not_just_first():
    selections = [
        ShotMediaSelection(scene_id=9, shot_id=9, mode="video"),
        ShotMediaSelection(scene_id=8, shot_id=8, mode="video"),
    ]
    with pytest.raises(VideoGenerationInputError) as exc:
        resolve_selected_shots(_prompt_set(), selections)
    assert "scene 9 shot 9" in str(exc.value)
    assert "scene 8 shot 8" in str(exc.value)


# ---- build_generation_request ----

def test_build_generation_request_copies_scene_and_shot_from_shot_prompt():
    shot_prompt = _shot_prompt(3, 4)
    request = build_generation_request(shot_prompt, output_dir="/media/video", options=VideoGenerationOptions())
    assert request.scene_id == 3
    assert request.shot_id == 4
    assert request.output_dir == "/media/video"


# ---- validate_generation_request ----

def test_validate_generation_request_passes_for_consistent_request():
    shot_prompt = _shot_prompt(1, 1)
    request = build_generation_request(shot_prompt, output_dir="/media/video", options=VideoGenerationOptions())
    validate_generation_request(request)  # should not raise


def test_validate_generation_request_rejects_mismatched_scene_shot():
    shot_prompt = _shot_prompt(1, 1)
    request = build_generation_request(shot_prompt, output_dir="/media/video", options=VideoGenerationOptions())
    bad_request = request.model_copy(update={"scene_id": 99})
    with pytest.raises(VideoGenerationInputError):
        validate_generation_request(bad_request)


def test_validate_generation_request_rejects_empty_output_dir():
    shot_prompt = _shot_prompt(1, 1)
    request = build_generation_request(shot_prompt, output_dir="", options=VideoGenerationOptions())
    with pytest.raises(VideoGenerationInputError):
        validate_generation_request(request)

import json
import sys

import pytest

import app as app_module
from config import settings


class FakeLLMClient:
    """Returns canned JSON responses in call order - the pipeline is strictly
    sequential (no concurrency), so call order reliably identifies which agent
    is asking without needing to sniff prompt text."""

    model_name = "fake-llm"

    def __init__(self, responses):
        self._responses = iter(responses)

    def generate(self, prompt, **kwargs):
        try:
            return next(self._responses)
        except StopIteration:
            raise AssertionError(
                f"FakeLLMClient ran out of canned responses; unexpected extra call with prompt:\n{prompt[:200]}"
            )


class FakeImageClient:
    """Returns fake image bytes that still satisfy validate_image_file's
    5000-byte floor, without touching a real image-generation API."""

    def generate_image(self, prompt):
        return b"FAKEPNGDATA" * 500  # 5500 bytes


SHOT_1_IMAGE_PROMPT = "Mira stands at the edge of a misty pine forest at dawn, wide shot, cinematic lighting, realistic style"
SHOT_1_MOTION_PROMPT = "Camera holds static as mist drifts slowly through the trees"
SHOT_2_IMAGE_PROMPT = "Close-up of Mira's determined face, green eyes catching the dawn light, cinematic realism"
SHOT_2_MOTION_PROMPT = "Slow zoom in on Mira's face as her expression firms with resolve"


def _story_response():
    return json.dumps(
        {
            "title": "Test Story",
            "logline": "A test story for pipeline verification",
            "theme": "courage",
            "target_duration_seconds": 30,
            "tone": "uplifting",
            "characters": [
                {"name": "Mira", "role": "protagonist", "one_line_description": "A brave explorer"}
            ],
            "scenes": [
                {
                    "scene_id": 1,
                    "title": "The Journey Begins",
                    "summary": "Mira starts her journey",
                    "setting": "forest",
                    "mood": "hopeful",
                    "characters_present": ["Mira"],
                    "estimated_duration_seconds": 30,
                }
            ],
        }
    )


def _scene_response():
    return json.dumps(
        {
            "scene_plans": [
                {
                    "scene_id": 1,
                    "shots": [
                        {
                            "shot_id": 1,
                            "camera_angle": "wide shot",
                            "camera_movement": "static",
                            "description": "Mira stands at the edge of the forest",
                            "characters_in_shot": ["Mira"],
                            "duration_seconds": 15,
                        },
                        {
                            "shot_id": 2,
                            "camera_angle": "close-up",
                            "camera_movement": "slow zoom in",
                            "description": "Mira looks determined",
                            "characters_in_shot": ["Mira"],
                            "duration_seconds": 15,
                        },
                    ],
                }
            ]
        }
    )


def _character_response():
    return json.dumps(
        {
            "character_profiles": [
                {
                    "name": "Mira",
                    "age_range": "20-25",
                    "build": "athletic",
                    "face_details": "sharp jawline, green eyes",
                    "hair": "short brown hair",
                    "outfit": "leather jacket and boots",
                    "color_palette": ["brown", "green"],
                    "distinguishing_features": "a scar above her left eyebrow",
                    "art_style_keywords": ["cinematic", "realistic"],
                    "reference_prompt": (
                        "A brave young woman with short brown hair and green eyes, "
                        "wearing a leather jacket, cinematic lighting"
                    ),
                }
            ]
        }
    )


def _environment_response():
    return json.dumps(
        {
            "environment_profiles": [
                {
                    "setting": "forest",
                    "time_of_day": "dawn",
                    "weather": "misty",
                    "key_visual_elements": ["tall pine trees", "fog"],
                    "color_palette": ["dark green", "grey"],
                    "lighting": "soft diffused light",
                    "atmosphere": "mysterious and calm",
                    "art_style_keywords": ["cinematic", "realistic"],
                    "reference_prompt": (
                        "A misty pine forest at dawn with soft diffused light filtering "
                        "through fog, cinematic realism"
                    ),
                }
            ]
        }
    )


def _shot_response(image_prompt, video_motion_prompt):
    return json.dumps({"image_prompt": image_prompt, "video_motion_prompt": video_motion_prompt})


def _happy_path_responses():
    return [
        _story_response(),
        _scene_response(),
        _character_response(),
        _environment_response(),
        _shot_response(SHOT_1_IMAGE_PROMPT, SHOT_1_MOTION_PROMPT),
        _shot_response(SHOT_2_IMAGE_PROMPT, SHOT_2_MOTION_PROMPT),
    ]


def _run_app(monkeypatch, tmp_path, argv, responses):
    fake_llm = FakeLLMClient(responses)
    monkeypatch.setattr(app_module, "LLMClient", lambda: fake_llm)
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", argv)
    app_module.main()


def test_full_pipeline_skip_images(monkeypatch, tmp_path):
    _run_app(
        monkeypatch,
        tmp_path,
        ["app.py", "--idea", "A brave explorer", "--duration", "30", "--skip-images"],
        _happy_path_responses(),
    )

    plan_files = list(tmp_path.glob("production_plan_*.json"))
    assert len(plan_files) == 1
    plan = json.loads(plan_files[0].read_text())
    assert plan["title"] == "Test Story"
    assert len(plan["scenes"]) == 1
    assert len(plan["characters"]) == 1

    storyboard_files = list(tmp_path.glob("storyboard_*.json"))
    assert len(storyboard_files) == 1
    storyboard = json.loads(storyboard_files[0].read_text())
    assert len(storyboard["scene_plans"]) == 1
    assert len(storyboard["scene_plans"][0]["shots"]) == 2

    character_files = list(tmp_path.glob("character_sheet_*.json"))
    assert len(character_files) == 1
    character_sheet = json.loads(character_files[0].read_text())
    assert character_sheet["character_profiles"][0]["name"] == "Mira"

    environment_files = list(tmp_path.glob("environment_sheet_*.json"))
    assert len(environment_files) == 1
    environment_sheet = json.loads(environment_files[0].read_text())
    assert environment_sheet["environment_profiles"][0]["setting"] == "forest"

    prompt_set_files = list(tmp_path.glob("prompt_set_*.json"))
    assert len(prompt_set_files) == 1
    prompt_set = json.loads(prompt_set_files[0].read_text())
    shots = sorted(prompt_set["shots"], key=lambda s: s["shot_id"])
    assert len(shots) == 2

    assert shots[0]["scene_id"] == 1
    assert shots[0]["shot_id"] == 1
    assert shots[0]["duration_seconds"] == 15
    assert shots[0]["image_prompt"] == SHOT_1_IMAGE_PROMPT
    assert shots[0]["video_motion_prompt"] == SHOT_1_MOTION_PROMPT

    assert shots[1]["scene_id"] == 1
    assert shots[1]["shot_id"] == 2
    assert shots[1]["duration_seconds"] == 15
    assert shots[1]["image_prompt"] == SHOT_2_IMAGE_PROMPT
    assert shots[1]["video_motion_prompt"] == SHOT_2_MOTION_PROMPT

    # --skip-images must not construct or touch the image pipeline at all.
    assert not list(tmp_path.glob("image_manifest.json"))
    assert not (tmp_path / "images").exists()


def test_full_pipeline_with_image_generation(monkeypatch, tmp_path):
    fake_image_client = FakeImageClient()
    monkeypatch.setattr(app_module, "GeminiImageClient", lambda: fake_image_client)

    _run_app(
        monkeypatch,
        tmp_path,
        ["app.py", "--idea", "A brave explorer", "--duration", "30"],
        _happy_path_responses(),
    )

    manifest_path = tmp_path / "image_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["assets"]) == 1  # one image per scene; this story has one scene

    asset = manifest["assets"][0]
    assert asset["scene_id"] == 1
    assert asset["prompt_used"] == SHOT_1_IMAGE_PROMPT  # scene's first shot is representative

    image_path = tmp_path / "images" / "scene_1.png"
    assert image_path.exists()
    assert image_path.stat().st_size >= 5_000


def test_pipeline_stops_on_story_planner_failure(monkeypatch, tmp_path):
    """A validator failure must still fail the whole run (SystemExit(1)), not
    continue with partial data - this is the fail-fast behavior ARCHITECTURE.md
    §13 requires future refactors to preserve."""
    bad_story_response = json.dumps(
        {
            "title": "Broken Story",
            "logline": "This story has no scenes",
            "theme": "n/a",
            "target_duration_seconds": 30,
            "tone": "n/a",
            "characters": [],
            "scenes": [],
        }
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_app(
            monkeypatch,
            tmp_path,
            ["app.py", "--idea", "A story that fails", "--duration", "30", "--skip-images"],
            [bad_story_response],
        )
    assert exc_info.value.code == 1

    # nothing should have been written - the run failed on the very first stage
    assert list(tmp_path.iterdir()) == []

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


def _assert_production_package(tmp_path, plan):
    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_dir = project_dirs[0]
    project_id = project_dir.name

    project_file = json.loads((project_dir / "project.json").read_text())
    assert project_file["project_id"] == project_id
    assert project_file["status"] == "PACKAGE_READY"
    assert project_file["source_plan_id"] == plan["plan_id"]

    package_dir = project_dir / "production-package"
    assert package_dir.exists()

    manifest = json.loads((package_dir / "manifest.json").read_text())
    assert manifest["package_id"] == project_id
    file_statuses = {f["name"]: f["status"] for f in manifest["files"]}
    assert file_statuses["voice_script.txt"] == "pending"
    assert set(file_statuses) == {
        "metadata.json", "story.md", "scene_plan.json", "shot_plan.json", "camera_plan.json",
        "character_bible.json", "environment_bible.json", "image_prompts.json",
        "video_prompts.json", "voice_script.txt",
    }
    for name in file_statuses:
        assert (package_dir / name).exists()

    metadata = json.loads((package_dir / "metadata.json").read_text())
    assert metadata["package_id"] == project_id
    assert metadata["source_plan_id"] == plan["plan_id"]
    assert metadata["target_duration_seconds"] == 30

    assert (package_dir / "story.md").read_text().startswith("# Test Story")

    scene_plan = json.loads((package_dir / "scene_plan.json").read_text())
    assert len(scene_plan) == 1
    assert scene_plan[0]["scene_id"] == 1
    assert scene_plan[0]["characters_present"] == ["Mira"]

    shot_plan = json.loads((package_dir / "shot_plan.json").read_text())
    assert len(shot_plan[0]["shots"]) == 2
    assert "camera_angle" not in shot_plan[0]["shots"][0]

    camera_plan = json.loads((package_dir / "camera_plan.json").read_text())
    assert camera_plan[0]["shots"][0]["camera_angle"] == "wide shot"
    assert camera_plan[0]["shots"][0]["camera_movement"] == "static"

    character_bible = json.loads((package_dir / "character_bible.json").read_text())
    assert character_bible["character_profiles"][0]["name"] == "Mira"

    environment_bible = json.loads((package_dir / "environment_bible.json").read_text())
    assert environment_bible["environment_profiles"][0]["setting"] == "forest"

    image_prompts = json.loads((package_dir / "image_prompts.json").read_text())
    assert image_prompts[0]["image_prompt"] == SHOT_1_IMAGE_PROMPT

    video_prompts = json.loads((package_dir / "video_prompts.json").read_text())
    assert video_prompts[0]["video_motion_prompt"] == SHOT_1_MOTION_PROMPT

    voice_script_text = (package_dir / "voice_script.txt").read_text()
    assert "pending" in voice_script_text.lower()


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

    _assert_production_package(tmp_path, plan)


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

    plan_files = list(tmp_path.glob("production_plan_*.json"))
    plan = json.loads(plan_files[0].read_text())
    _assert_production_package(tmp_path, plan)


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

    # Project Manager creates the project scaffold before Story Planner even
    # runs, so a project.json exists - but no stage artifacts, since the run
    # failed on the very first stage and never advanced past CREATED.
    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_file = json.loads((project_dirs[0] / "project.json").read_text())
    assert project_file["status"] == "CREATED"
    assert project_file["source_plan_id"] is None

    assert list(tmp_path.glob("production_plan_*.json")) == []
    assert not (project_dirs[0] / "production-package").exists()

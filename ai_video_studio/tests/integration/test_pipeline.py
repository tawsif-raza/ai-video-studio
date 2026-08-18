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


def _research_response():
    return json.dumps(
        {
            "key_facts": ["Explorers often travel at dawn to avoid midday heat"],
            "considerations": ["Keep the tone hopeful, not grim"],
        }
    )


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
                            "description": "Mira stands at the edge of the forest",
                            "characters_in_shot": ["Mira"],
                            "duration_seconds": 15,
                        },
                        {
                            "shot_id": 2,
                            "description": "Mira looks determined",
                            "characters_in_shot": ["Mira"],
                            "duration_seconds": 15,
                        },
                    ],
                }
            ]
        }
    )


def _shot_planner_response():
    return json.dumps(
        {
            "scene_plans": [
                {
                    "scene_id": 1,
                    "shots": [
                        {
                            "shot_id": 1,
                            "description": "Mira stands at the edge of the forest",
                            "characters_in_shot": ["Mira"],
                            "duration_seconds": 15,
                        },
                        {
                            "shot_id": 2,
                            "description": "Mira looks determined",
                            "characters_in_shot": ["Mira"],
                            "duration_seconds": 15,
                        },
                    ],
                }
            ]
        }
    )


def _camera_planner_response():
    return json.dumps(
        {
            "scene_plans": [
                {
                    "scene_id": 1,
                    "shots": [
                        {"shot_id": 1, "camera_angle": "wide shot", "camera_movement": "static"},
                        {"shot_id": 2, "camera_angle": "close-up", "camera_movement": "slow zoom in"},
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


VOICE_SCRIPT_NARRATION = "Mira steps into the misty forest, ready for what lies ahead."


def _voice_script_response():
    return json.dumps({"lines": [{"scene_id": 1, "narration_text": VOICE_SCRIPT_NARRATION}]})


def _happy_path_responses():
    return [
        _research_response(),
        _story_response(),
        _scene_response(),
        _shot_planner_response(),
        _camera_planner_response(),
        _character_response(),
        _environment_response(),
        _shot_response(SHOT_1_IMAGE_PROMPT, SHOT_1_MOTION_PROMPT),
        _shot_response(SHOT_2_IMAGE_PROMPT, SHOT_2_MOTION_PROMPT),
        _voice_script_response(),
    ]


def _assert_production_package(tmp_path, plan, research_status="generated"):
    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_dir = project_dirs[0]
    project_id = project_dir.name

    project_file = json.loads((project_dir / "project.json").read_text())
    assert project_file["project_id"] == project_id
    assert project_file["status"] == "PACKAGE_READY"
    assert project_file["source_plan_id"] == plan["plan_id"]
    if research_status == "generated":
        assert project_file["source_research_brief_id"] is not None
    else:
        assert project_file["source_research_brief_id"] is None

    package_dir = project_dir / "production-package"
    assert package_dir.exists()

    manifest = json.loads((package_dir / "manifest.json").read_text())
    assert manifest["package_id"] == project_id
    file_statuses = {f["name"]: f["status"] for f in manifest["files"]}
    assert file_statuses["voice_script.txt"] == "generated"
    assert file_statuses["research_brief.json"] == research_status
    assert set(file_statuses) == {
        "metadata.json", "research_brief.json", "story.md", "scene_plan.json", "shot_plan.json",
        "camera_plan.json", "character_bible.json", "environment_bible.json", "image_prompts.json",
        "video_prompts.json", "voice_script.txt",
    }
    for name in file_statuses:
        assert (package_dir / name).exists()

    research_brief = json.loads((package_dir / "research_brief.json").read_text())
    if research_status == "generated":
        assert research_brief["key_facts"] == ["Explorers often travel at dawn to avoid midday heat"]
        assert research_brief["considerations"] == ["Keep the tone hopeful, not grim"]
    else:
        assert research_brief["status"] == "skipped"

    # research_brief.json must never leak into a flat legacy output location -
    # it only ever exists inside the Production Package.
    assert list(tmp_path.glob("research_brief_*.json")) == []

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
    assert voice_script_text == VOICE_SCRIPT_NARRATION


def _run_app(monkeypatch, tmp_path, argv, responses):
    fake_llm = FakeLLMClient(responses)
    monkeypatch.setattr(app_module, "LLMClient", lambda: fake_llm)
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", argv)
    app_module.main()


def test_full_pipeline_default_skips_images(monkeypatch, tmp_path):
    """Image generation is opt-in (ARCHITECTURE.md SS2/SS15 Phase 6) - a default
    run with zero image-related flags must never construct the image pipeline."""
    _run_app(
        monkeypatch,
        tmp_path,
        ["app.py", "--idea", "A brave explorer", "--duration", "30"],
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

    # Default run (no --generate-images) must not construct or touch the image
    # pipeline at all.
    assert not list(tmp_path.glob("image_manifest.json"))
    assert not (tmp_path / "images").exists()

    _assert_production_package(tmp_path, plan)


def test_skip_images_flag_is_a_deprecated_no_op(monkeypatch, tmp_path, caplog):
    """--skip-images predates the opt-in default (Phase 6) and is kept only so
    existing scripts don't break - it must still result in no image generation,
    with a deprecation warning logged, and must not require --generate-images
    to also be absent."""
    with caplog.at_level("WARNING"):
        _run_app(
            monkeypatch,
            tmp_path,
            ["app.py", "--idea", "A brave explorer", "--duration", "30", "--skip-images"],
            _happy_path_responses(),
        )

    assert not list(tmp_path.glob("image_manifest.json"))
    assert not (tmp_path / "images").exists()
    assert any("--skip-images is deprecated" in record.message for record in caplog.records)


def test_full_pipeline_skip_research(monkeypatch, tmp_path):
    """--skip-research must bypass the Research stage entirely: no research
    canned response consumed, and the exported package still contains
    research_brief.json but marked 'skipped' rather than 'generated' -
    the manifest always lists it as part of the Production Package."""
    _run_app(
        monkeypatch,
        tmp_path,
        ["app.py", "--idea", "A brave explorer", "--duration", "30", "--skip-research"],
        [_story_response(), _scene_response(), _shot_planner_response(), _camera_planner_response(),
         _character_response(), _environment_response(),
         _shot_response(SHOT_1_IMAGE_PROMPT, SHOT_1_MOTION_PROMPT),
         _shot_response(SHOT_2_IMAGE_PROMPT, SHOT_2_MOTION_PROMPT),
         _voice_script_response()],
    )

    plan_files = list(tmp_path.glob("production_plan_*.json"))
    plan = json.loads(plan_files[0].read_text())

    project_dirs = list((tmp_path / "projects").iterdir())
    project_file = json.loads((project_dirs[0] / "project.json").read_text())
    assert project_file["source_research_brief_id"] is None
    assert project_file["status"] == "PACKAGE_READY"

    _assert_production_package(tmp_path, plan, research_status="skipped")


def test_full_pipeline_with_image_generation(monkeypatch, tmp_path):
    """Image generation only runs when explicitly opted into via --generate-images
    (ARCHITECTURE.md SS2/SS15 Phase 6) - it is a manual tool, not a default stage."""
    fake_image_client = FakeImageClient()
    monkeypatch.setattr(app_module, "GeminiImageClient", lambda: fake_image_client)

    _run_app(
        monkeypatch,
        tmp_path,
        ["app.py", "--idea", "A brave explorer", "--duration", "30", "--generate-images"],
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
            ["app.py", "--idea", "A story that fails", "--duration", "30", "--skip-images", "--skip-research"],
            [bad_story_response],
        )
    assert exc_info.value.code == 1

    # --skip-research isolates this test to Story Planner: Project Manager
    # creates the project scaffold before Story Planner even runs, so a
    # project.json exists - but no stage artifacts, since the run failed on
    # the very first stage and never advanced past CREATED.
    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_file = json.loads((project_dirs[0] / "project.json").read_text())
    assert project_file["status"] == "CREATED"
    assert project_file["source_research_brief_id"] is None
    assert project_file["source_plan_id"] is None

    assert list(tmp_path.glob("production_plan_*.json")) == []
    assert not (project_dirs[0] / "production-package").exists()


def test_pipeline_stops_on_research_failure(monkeypatch, tmp_path):
    """Research runs by default (Node 0) - a validator failure there must
    fail fast exactly like every other stage (ARCHITECTURE.md §13), before
    Story Planner ever runs."""
    bad_research_response = json.dumps({"key_facts": [], "considerations": []})

    with pytest.raises(SystemExit) as exc_info:
        _run_app(
            monkeypatch,
            tmp_path,
            ["app.py", "--idea", "A story that fails", "--duration", "30", "--skip-images"],
            [bad_research_response],
        )
    assert exc_info.value.code == 1

    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_file = json.loads((project_dirs[0] / "project.json").read_text())
    assert project_file["status"] == "CREATED"
    assert project_file["source_research_brief_id"] is None

    assert list(tmp_path.glob("production_plan_*.json")) == []
    assert not (project_dirs[0] / "production-package").exists()


def _n_scene_story_response(scene_count, duration, char_name="Mira"):
    per_scene = duration // scene_count
    return json.dumps(
        {
            "title": "Test Story",
            "logline": "A test story for pipeline verification",
            "theme": "courage",
            "target_duration_seconds": duration,
            "tone": "uplifting",
            "characters": [{"name": char_name, "role": "protagonist", "one_line_description": "A brave explorer"}],
            "scenes": [
                {
                    "scene_id": i,
                    "title": f"Scene {i}",
                    "summary": f"Beat {i} of the journey",
                    "setting": "forest",
                    "mood": "hopeful",
                    "characters_present": [char_name],
                    "estimated_duration_seconds": per_scene,
                }
                for i in range(1, scene_count + 1)
            ],
        }
    )


def _n_scene_one_shot_each_response(scene_count, shot_duration, char_name="Mira"):
    """Shared shape for both Scene Planner and Shot Planner responses - one
    shot per scene, sequentially numbered shot_ids across the whole story."""
    return json.dumps(
        {
            "scene_plans": [
                {
                    "scene_id": i,
                    "shots": [
                        {
                            "shot_id": i,
                            "description": f"{char_name} acts in scene {i}",
                            "characters_in_shot": [char_name],
                            "duration_seconds": shot_duration,
                        }
                    ],
                }
                for i in range(1, scene_count + 1)
            ]
        }
    )


def _n_scene_camera_response(scene_count):
    # Alternates between two distinct camera treatments - CameraPlannerAgent's
    # validator (agents/camera_planner/validator.py) rejects a plan that
    # assigns the identical angle+movement to every shot once there are more
    # than two shots total.
    treatments = [("wide shot", "static"), ("close-up", "slow zoom in")]
    return json.dumps(
        {
            "scene_plans": [
                {
                    "scene_id": i,
                    "shots": [
                        {
                            "shot_id": i,
                            "camera_angle": treatments[i % 2][0],
                            "camera_movement": treatments[i % 2][1],
                        }
                    ],
                }
                for i in range(1, scene_count + 1)
            ]
        }
    )


def _n_scene_voice_script_response(scene_count, char_name="Mira"):
    return json.dumps(
        {
            "lines": [
                {"scene_id": i, "narration_text": f"{char_name} moves through scene {i}."}
                for i in range(1, scene_count + 1)
            ]
        }
    )


def test_custom_scene_count_survives_full_pipeline_and_duration_does_not_override_it(monkeypatch, tmp_path):
    """Section 13 Test 6 (duration conflict), run end to end through the
    real CLI/controller pipeline: duration_seconds=150 alone would nudge
    the Story Planner toward its usual ~20-21 scene default, but an
    explicit --scene-count-mode=custom --scene-count=10 must produce
    exactly 10 scenes in the final production plan/storyboard/shot plan -
    never falling back toward the default count."""
    scene_count = 10
    duration = 150
    per_scene_duration = duration // scene_count  # 15s/scene, within ShotBrief's 1-15s bound

    responses = [
        _n_scene_story_response(scene_count, duration),
        _n_scene_one_shot_each_response(scene_count, per_scene_duration),  # Scene Planner
        _n_scene_one_shot_each_response(scene_count, per_scene_duration),  # Shot Planner
        _n_scene_camera_response(scene_count),
        _character_response(),
        _environment_response(),
    ]
    for i in range(1, scene_count + 1):
        responses.append(
            _shot_response(
                f"A cinematic wide shot of Mira in the misty forest, beat number {i} of the journey",
                f"Camera slowly pushes in as Mira reacts during beat number {i} of the journey",
            )
        )
    responses.append(_n_scene_voice_script_response(scene_count))

    _run_app(
        monkeypatch,
        tmp_path,
        [
            "app.py", "--idea", "A brave explorer", "--duration", str(duration),
            "--skip-research", "--scene-count-mode", "custom", "--scene-count", str(scene_count),
        ],
        responses,
    )

    plan_files = list(tmp_path.glob("production_plan_*.json"))
    assert len(plan_files) == 1
    plan = json.loads(plan_files[0].read_text())
    assert len(plan["scenes"]) == scene_count
    assert plan["scene_count_mode"] == "custom"
    assert plan["scene_count"] == scene_count

    storyboard_files = list(tmp_path.glob("storyboard_*.json"))
    storyboard = json.loads(storyboard_files[0].read_text())
    assert len(storyboard["scene_plans"]) == scene_count

    project_dirs = list((tmp_path / "projects").iterdir())
    package_dir = project_dirs[0] / "production-package"
    metadata = json.loads((package_dir / "metadata.json").read_text())
    assert metadata["scene_count_mode"] == "custom"
    assert metadata["requested_scene_count"] == scene_count
    assert metadata["generated_scene_count"] == scene_count

    scene_plan = json.loads((package_dir / "scene_plan.json").read_text())
    assert len(scene_plan) == scene_count


def test_default_scene_count_unaffected_by_custom_scene_count_plumbing(monkeypatch, tmp_path):
    """Backward compatibility (section 10): a run with no scene-count flags
    at all must behave exactly as before - scene_count_mode defaults to
    'default' and scene_count stays null on the persisted plan."""
    _run_app(
        monkeypatch,
        tmp_path,
        ["app.py", "--idea", "A brave explorer", "--duration", "30"],
        _happy_path_responses(),
    )

    plan_files = list(tmp_path.glob("production_plan_*.json"))
    plan = json.loads(plan_files[0].read_text())
    assert plan["scene_count_mode"] == "default"
    assert plan["scene_count"] is None


def test_pipeline_stops_on_voice_script_failure(monkeypatch, tmp_path):
    """Voice Script runs last, after Prompt Intelligence - a validator failure
    there must still fail fast (ARCHITECTURE.md §13) rather than exporting a
    Production Package with a missing/invalid voice_script.txt."""
    bad_voice_script_response = json.dumps({"lines": []})

    with pytest.raises(SystemExit) as exc_info:
        _run_app(
            monkeypatch,
            tmp_path,
            ["app.py", "--idea", "A brave explorer", "--duration", "30", "--skip-images", "--skip-research"],
            [_story_response(), _scene_response(), _shot_planner_response(), _camera_planner_response(),
             _character_response(), _environment_response(),
             _shot_response(SHOT_1_IMAGE_PROMPT, SHOT_1_MOTION_PROMPT),
             _shot_response(SHOT_2_IMAGE_PROMPT, SHOT_2_MOTION_PROMPT),
             bad_voice_script_response],
        )
    assert exc_info.value.code == 1

    project_dirs = list((tmp_path / "projects").iterdir())
    assert len(project_dirs) == 1
    project_file = json.loads((project_dirs[0] / "project.json").read_text())
    assert project_file["status"] == "ENVIRONMENTS_COMPLETE"
    assert project_file["source_prompt_set_id"] is not None
    assert project_file["source_voice_script_id"] is None

    assert not (project_dirs[0] / "production-package").exists()

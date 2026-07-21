import json
from pathlib import Path

from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
from agents.prompt_generator.contract import PromptSet, ShotPrompt
from agents.scene_planner.contract import Storyboard
from agents.scene_planner.schema import ScenePlan, ShotBrief
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief
from config import settings
from project_manager.manager import ProjectManager
from project_manager.project import ProjectState


def _make_plan():
    return ProductionPlan(
        title="Test", logline="A test", theme="courage",
        target_duration_seconds=30, tone="uplifting",
        characters=[CharacterBrief(name="Mira", role="protagonist", one_line_description="brave")],
        scenes=[
            SceneBrief(
                scene_id=1, title="Opening", summary="Mira starts",
                setting="Forest clearing", mood="hopeful",
                characters_present=["Mira"], estimated_duration_seconds=30,
            )
        ],
        source_idea="test idea",
    )


def _make_storyboard(plan):
    return Storyboard(
        scene_plans=[
            ScenePlan(
                scene_id=1,
                shots=[
                    ShotBrief(
                        shot_id=1, camera_angle="wide shot", camera_movement="static",
                        description="Mira stands at the forest edge", characters_in_shot=["Mira"],
                        duration_seconds=15,
                    )
                ],
            )
        ],
        source_plan_id=plan.plan_id,
    )


def _make_character_sheet(plan):
    return CharacterSheet(
        character_profiles=[
            CharacterVisualProfile(
                name="Mira", age_range="mid-20s", build="lean", face_details="warm eyes",
                hair="black hair", outfit="green tunic", color_palette=["green", "brown"],
                distinguishing_features="a scar", art_style_keywords=["3D animated"],
                reference_prompt="A lean young woman with black hair and warm eyes in a green tunic.",
            )
        ],
        source_plan_id=plan.plan_id,
    )


def _make_environment_sheet(plan):
    return EnvironmentSheet(
        environment_profiles=[
            EnvironmentProfile(
                setting="Forest clearing", time_of_day="dawn", weather="misty",
                key_visual_elements=["tall trees"], color_palette=["green", "grey"],
                lighting="soft morning light", atmosphere="peaceful",
                art_style_keywords=["3D animated"],
                reference_prompt="A misty forest clearing at dawn with tall trees and soft morning light.",
            )
        ],
        source_plan_id=plan.plan_id,
    )


def _make_prompt_set(storyboard):
    return PromptSet(
        source_storyboard_id=storyboard.storyboard_id,
        shots=[
            ShotPrompt(
                scene_id=1, shot_id=1, duration_seconds=15,
                image_prompt="Mira stands at the misty forest edge, wide shot, cinematic lighting, realism.",
                video_motion_prompt="Camera holds static as mist drifts through the trees.",
            )
        ],
    )


def test_create_project_writes_project_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    project = manager.create_project()

    assert project.status == ProjectState.CREATED
    project_file = tmp_path / "projects" / project.project_id / "project.json"
    assert project_file.exists()
    assert json.loads(project_file.read_text())["project_id"] == project.project_id


def test_load_project_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    created = manager.create_project()

    loaded = manager.load_project(created.project_id)

    assert loaded == created


def test_save_story_plan_advances_state_and_writes_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    plan = _make_plan()

    project = manager.save_story_plan(project, plan)

    assert project.status == ProjectState.STORY_COMPLETE
    assert project.source_plan_id == plan.plan_id
    legacy_file = tmp_path / f"production_plan_{plan.plan_id}.json"
    assert legacy_file.exists()
    assert json.loads(legacy_file.read_text())["title"] == "Test"


def test_full_stage_sequence_reaches_package_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    plan = _make_plan()
    project = manager.save_story_plan(project, plan)

    storyboard = _make_storyboard(plan)
    project = manager.save_storyboard(project, storyboard)

    character_sheet = _make_character_sheet(plan)
    project = manager.save_character_sheet(project, character_sheet)

    environment_sheet = _make_environment_sheet(plan)
    project = manager.save_environment_sheet(project, environment_sheet)

    prompt_set = _make_prompt_set(storyboard)
    project = manager.save_prompt_set(project, prompt_set)

    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, character_sheet=character_sheet,
        environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone="uplifting", audience=None, art_style=None,
    )

    assert project.status == ProjectState.PACKAGE_READY
    assert project.production_package_dir is not None
    package_dir = tmp_path / "projects" / project.project_id / "production-package"
    assert package_dir == Path(project.production_package_dir)
    assert (package_dir / "manifest.json").exists()

    # project.json on disk reflects the final state, not an intermediate one
    saved = json.loads((tmp_path / "projects" / project.project_id / "project.json").read_text())
    assert saved["status"] == "PACKAGE_READY"
    assert saved["source_storyboard_id"] == storyboard.storyboard_id
    assert saved["source_character_sheet_id"] == character_sheet.sheet_id
    assert saved["source_environment_sheet_id"] == environment_sheet.sheet_id
    assert saved["source_prompt_set_id"] == prompt_set.prompt_set_id


def test_save_image_manifest_writes_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    project = manager.save_image_manifest(project, {"assets": []})

    legacy_file = tmp_path / "image_manifest.json"
    assert legacy_file.exists()
    assert project.image_manifest_path == str(legacy_file)


def test_get_images_dir_returns_flat_legacy_location(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    assert manager.get_images_dir(project) == tmp_path / "images"

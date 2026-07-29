import uuid

from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.camera_plan import CameraPlan, CameraScenePlan, CameraShot
from shared_core.contracts.character_sheet import CharacterSheet, CharacterVisualProfile
from shared_core.contracts.environment_sheet import EnvironmentProfile, EnvironmentSheet
from shared_core.contracts.production_plan import CharacterBrief, ProductionPlan, SceneBrief
from shared_core.contracts.prompt_set import PromptSet, ShotPrompt
from shared_core.contracts.shot_plan import ShotItem, ShotPlan, ShotScenePlan
from shared_core.contracts.storyboard import ScenePlan, ShotBrief, Storyboard
from shared_core.contracts.timeline import Timeline, TimelineClip
from web_api.dependencies import get_project_manager


def _build_production_ready_project(project_manager):
    project = project_manager.create_project()
    plan = ProductionPlan(
        title="Test", logline="A test", theme="courage", target_duration_seconds=15, tone="uplifting",
        characters=[CharacterBrief(name="Mira", role="protagonist", one_line_description="brave")],
        scenes=[SceneBrief(
            scene_id=1, title="Opening", summary="Mira starts", setting="Forest clearing", mood="hopeful",
            characters_present=["Mira"], estimated_duration_seconds=15,
        )],
        source_idea="test idea",
    )
    storyboard = Storyboard(
        scene_plans=[ScenePlan(scene_id=1, shots=[
            ShotBrief(shot_id=1, description="Mira at the edge", characters_in_shot=["Mira"], duration_seconds=15),
        ])],
        source_plan_id=plan.plan_id,
    )
    shot_plan = ShotPlan(
        scene_plans=[ShotScenePlan(scene_id=1, shots=[
            ShotItem(shot_id=1, description="Mira at the edge", characters_in_shot=["Mira"], duration_seconds=15),
        ])],
        source_storyboard_id=storyboard.storyboard_id,
    )
    camera_plan = CameraPlan(
        scene_plans=[CameraScenePlan(scene_id=1, shots=[
            CameraShot(shot_id=1, camera_angle="wide shot", camera_movement="static"),
        ])],
        source_shot_plan_id=shot_plan.shot_plan_id,
    )
    character_sheet = CharacterSheet(
        character_profiles=[CharacterVisualProfile(
            name="Mira", age_range="mid-20s", build="lean", face_details="warm eyes", hair="black hair",
            outfit="green tunic", color_palette=["green", "brown"], distinguishing_features="a scar",
            art_style_keywords=["3D animated"],
            reference_prompt="A lean young woman with black hair and warm eyes in a green tunic.",
        )],
        source_plan_id=plan.plan_id,
    )
    environment_sheet = EnvironmentSheet(
        environment_profiles=[EnvironmentProfile(
            setting="Forest clearing", time_of_day="dawn", weather="misty", key_visual_elements=["tall trees"],
            color_palette=["green", "grey"], lighting="soft morning light", atmosphere="peaceful",
            art_style_keywords=["3D animated"],
            reference_prompt="A misty forest clearing at dawn with tall trees and soft morning light.",
        )],
        source_plan_id=plan.plan_id,
    )
    prompt_set = PromptSet(
        source_storyboard_id=storyboard.storyboard_id,
        shots=[ShotPrompt(
            scene_id=1, shot_id=1, duration_seconds=15,
            image_prompt="Mira stands at the misty forest edge, wide shot, cinematic lighting, realism.",
            video_motion_prompt="Camera holds static as mist drifts through the trees.",
        )],
    )
    project = project_manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone="uplifting", audience=None, art_style=None,
    )
    return project


def _build_producer_ready_project(project_manager):
    project = project_manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(
        source_asset_manifest_id=manifest.manifest_id,
        clips=[TimelineClip(
            scene_id=1, shot_id=1, asset_path="/i/s1s1.png", asset_type="image",
            duration_seconds=5, start_time=0, end_time=5,
        )],
        total_duration_seconds=5,
    )
    project = project_manager.export_producer_package(project, asset_manifest=manifest, timeline=timeline)
    return project


def test_production_package_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/production-package")

    assert response.status_code == 404


def test_production_package_malformed_project_id_returns_422(client):
    response = client.get("/projects/not-a-uuid/production-package")

    assert response.status_code == 422


def test_production_package_not_yet_generated_returns_404(client, app_):
    project = get_project_manager().create_project()

    response = client.get(f"/projects/{project.project_id}/production-package")

    assert response.status_code == 404


def test_production_package_returns_structured_content_once_generated(client, app_):
    project = _build_production_ready_project(get_project_manager())

    response = client.get(f"/projects/{project.project_id}/production-package")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "manifest.json", "metadata.json", "research_brief.json", "story.md", "scene_plan.json",
        "shot_plan.json", "camera_plan.json", "character_bible.json", "environment_bible.json",
        "image_prompts.json", "video_prompts.json", "voice_script.txt",
    }
    assert body["character_bible.json"]["character_profiles"][0]["name"] == "Mira"
    assert body["story.md"].startswith("# Test")
    # no raw filesystem path anywhere in the response body
    assert project.production_package_dir not in response.text


def test_producer_package_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/producer-package")

    assert response.status_code == 404


def test_producer_package_not_yet_generated_returns_404(client, app_):
    project = get_project_manager().create_project()

    response = client.get(f"/projects/{project.project_id}/producer-package")

    assert response.status_code == 404


def test_producer_package_returns_structured_content_once_generated(client, app_):
    project = _build_producer_ready_project(get_project_manager())

    response = client.get(f"/projects/{project.project_id}/producer-package")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"manifest.json", "asset_manifest.json", "timeline_plan.json"}
    assert body["asset_manifest.json"]["is_valid"] is True
    assert body["timeline_plan.json"]["total_duration_seconds"] == 5
    assert project.producer_package_dir not in response.text

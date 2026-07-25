import json
from pathlib import Path

from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
from agents.prompt_generator.contract import PromptSet, ShotPrompt
from agents.research.contract import ResearchBrief
from agents.scene_planner.contract import Storyboard
from agents.scene_planner.schema import ScenePlan, ShotBrief
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief
from agents.voice_script.contract import VoiceScript
from agents.voice_script.schema import NarrationLine
from config import settings
from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.camera_plan import CameraPlan, CameraScenePlan, CameraShot
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata
from shared_core.contracts.thumbnail_plan import ThumbnailPlan
from shared_core.contracts.shot_plan import ShotItem, ShotPlan, ShotScenePlan
from shared_core.contracts.subtitle import SubtitleCue, SubtitlePlan
from shared_core.contracts.timeline import Timeline, TimelineClip


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
                        shot_id=1,
                        description="Mira stands at the forest edge", characters_in_shot=["Mira"],
                        duration_seconds=15,
                    )
                ],
            )
        ],
        source_plan_id=plan.plan_id,
    )


def _make_shot_plan(storyboard):
    return ShotPlan(
        scene_plans=[
            ShotScenePlan(
                scene_id=1,
                shots=[
                    ShotItem(
                        shot_id=1,
                        description="Mira stands at the forest edge", characters_in_shot=["Mira"],
                        duration_seconds=15,
                    )
                ],
            )
        ],
        source_storyboard_id=storyboard.storyboard_id,
    )


def _make_camera_plan(shot_plan):
    return CameraPlan(
        scene_plans=[
            CameraScenePlan(
                scene_id=1,
                shots=[CameraShot(shot_id=1, camera_angle="wide shot", camera_movement="static")],
            )
        ],
        source_shot_plan_id=shot_plan.shot_plan_id,
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


def _make_research_brief():
    return ResearchBrief(
        key_facts=["Explorers often travel at dawn to avoid midday heat"],
        considerations=["Keep the tone hopeful, not grim"],
        source_idea="test idea",
    )


def _make_voice_script(plan):
    return VoiceScript(
        lines=[NarrationLine(scene_id=1, narration_text="Mira starts her journey at dawn.")],
        source_plan_id=plan.plan_id,
    )


def test_save_research_brief_advances_state_without_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    brief = _make_research_brief()

    project = manager.save_research_brief(project, brief)

    assert project.status == ProjectState.RESEARCHED
    assert project.source_research_brief_id == brief.brief_id
    # Unlike every other save_* method, this must never write a flat file -
    # the brief only reaches disk via the Production Package.
    assert list(tmp_path.glob("research_brief_*.json")) == []


def test_save_voice_script_advances_state_without_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    plan = _make_plan()
    voice_script = _make_voice_script(plan)

    project = manager.save_voice_script(project, voice_script)

    assert project.status == ProjectState.PROMPTS_COMPLETE
    assert project.source_voice_script_id == voice_script.script_id
    # Like the research brief, this must never write a flat file - the voice
    # script only reaches disk via the Production Package.
    assert list(tmp_path.glob("voice_script_*.json")) == []


def test_save_shot_plan_advances_state_without_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)

    project = manager.save_shot_plan(project, shot_plan)

    assert project.status == ProjectState.SHOTS_COMPLETE
    assert project.source_shot_plan_id == shot_plan.shot_plan_id
    # Like research_brief/voice_script, this is a brand-new stage and deliberately
    # does not extend the legacy flat-outputs pattern - no flat file is written.
    assert list(tmp_path.glob("shot_plan_*.json")) == []


def test_save_camera_plan_advances_state_without_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)

    project = manager.save_camera_plan(project, camera_plan)

    assert project.status == ProjectState.CAMERA_COMPLETE
    assert project.source_camera_plan_id == camera_plan.camera_plan_id
    assert list(tmp_path.glob("camera_plan_*.json")) == []


def test_save_prompt_set_does_not_advance_to_prompts_complete(tmp_path, monkeypatch):
    """PROMPTS_COMPLETE requires Prompt Intelligence AND Voice Script (ARCHITECTURE.md
    §8) - save_prompt_set alone must leave status unchanged; save_voice_script is the
    one that actually crosses into PROMPTS_COMPLETE."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    project = manager.save_environment_sheet(project, _make_environment_sheet(plan))
    prompt_set = _make_prompt_set(storyboard)

    project = manager.save_prompt_set(project, prompt_set)

    assert project.status == ProjectState.ENVIRONMENTS_COMPLETE
    assert project.source_prompt_set_id == prompt_set.prompt_set_id


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

    shot_plan = _make_shot_plan(storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    assert project.status == ProjectState.SHOTS_COMPLETE

    camera_plan = _make_camera_plan(shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    assert project.status == ProjectState.CAMERA_COMPLETE

    character_sheet = _make_character_sheet(plan)
    project = manager.save_character_sheet(project, character_sheet)

    environment_sheet = _make_environment_sheet(plan)
    project = manager.save_environment_sheet(project, environment_sheet)

    prompt_set = _make_prompt_set(storyboard)
    project = manager.save_prompt_set(project, prompt_set)
    assert project.status == ProjectState.ENVIRONMENTS_COMPLETE  # save_prompt_set alone doesn't advance

    research_brief = _make_research_brief()
    project = manager.save_research_brief(project, research_brief)

    voice_script = _make_voice_script(plan)
    project = manager.save_voice_script(project, voice_script)
    assert project.status == ProjectState.PROMPTS_COMPLETE

    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        research_brief=research_brief, voice_script=voice_script, tone="uplifting", audience=None,
        art_style=None,
    )

    assert project.status == ProjectState.PACKAGE_READY
    assert project.production_package_dir is not None
    package_dir = tmp_path / "projects" / project.project_id / "production-package"
    assert package_dir == Path(project.production_package_dir)
    assert (package_dir / "manifest.json").exists()

    research_brief_file = package_dir / "research_brief.json"
    assert research_brief_file.exists()
    assert json.loads(research_brief_file.read_text())["key_facts"] == research_brief.key_facts

    voice_script_file = package_dir / "voice_script.txt"
    assert voice_script_file.exists()
    assert voice_script_file.read_text() == "Mira starts her journey at dawn."

    manifest = json.loads((package_dir / "manifest.json").read_text())
    file_statuses = {f["name"]: f["status"] for f in manifest["files"]}
    assert file_statuses["research_brief.json"] == "generated"
    assert file_statuses["voice_script.txt"] == "generated"

    # project.json on disk reflects the final state, not an intermediate one
    saved = json.loads((tmp_path / "projects" / project.project_id / "project.json").read_text())
    assert saved["status"] == "PACKAGE_READY"
    assert saved["source_research_brief_id"] == research_brief.brief_id
    assert saved["source_storyboard_id"] == storyboard.storyboard_id
    assert saved["source_shot_plan_id"] == shot_plan.shot_plan_id
    assert saved["source_camera_plan_id"] == camera_plan.camera_plan_id
    assert saved["source_character_sheet_id"] == character_sheet.sheet_id
    assert saved["source_environment_sheet_id"] == environment_sheet.sheet_id
    assert saved["source_prompt_set_id"] == prompt_set.prompt_set_id
    assert saved["source_voice_script_id"] == voice_script.script_id


def test_export_production_package_marks_research_skipped_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    plan = _make_plan()
    project = manager.save_story_plan(project, plan)
    storyboard = _make_storyboard(plan)
    project = manager.save_storyboard(project, storyboard)
    shot_plan = _make_shot_plan(storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    camera_plan = _make_camera_plan(shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    character_sheet = _make_character_sheet(plan)
    project = manager.save_character_sheet(project, character_sheet)
    environment_sheet = _make_environment_sheet(plan)
    project = manager.save_environment_sheet(project, environment_sheet)
    prompt_set = _make_prompt_set(storyboard)
    project = manager.save_prompt_set(project, prompt_set)

    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone="uplifting", audience=None, art_style=None,
    )

    package_dir = tmp_path / "projects" / project.project_id / "production-package"
    research_brief_file = package_dir / "research_brief.json"
    assert research_brief_file.exists()
    assert json.loads(research_brief_file.read_text())["status"] == "skipped"

    # voice_script omitted entirely (no save_voice_script call, no kwarg passed) -
    # export_production_package must still fall back to the pending stub.
    voice_script_file = package_dir / "voice_script.txt"
    assert voice_script_file.exists()
    assert "pending" in voice_script_file.read_text().lower()

    manifest = json.loads((package_dir / "manifest.json").read_text())
    file_statuses = {f["name"]: f["status"] for f in manifest["files"]}
    assert file_statuses["research_brief.json"] == "skipped"
    assert file_statuses["voice_script.txt"] == "pending"


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


def test_load_prompt_set_roundtrips_from_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    prompt_set = _make_prompt_set(storyboard)
    project = manager.save_prompt_set(project, prompt_set)

    loaded = manager.load_prompt_set(project)

    assert loaded.prompt_set_id == prompt_set.prompt_set_id
    assert loaded.shots[0].scene_id == 1
    assert loaded.shots[0].shot_id == 1


def test_get_media_dir_is_project_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    assert manager.get_media_dir(project) == tmp_path / "projects" / project.project_id / "media"


def test_scan_media_returns_empty_when_media_dir_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manifest = manager.scan_media(project)

    assert manifest.images == []
    assert manifest.videos == []
    assert manifest.audio == []


def test_scan_media_discovers_files_with_hash_and_size(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    images_dir = manager.get_media_dir(project) / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "scene_1_shot_1.png").write_bytes(b"0" * 6000)

    manifest = manager.scan_media(project)

    assert len(manifest.images) == 1
    assert manifest.images[0].filename == "scene_1_shot_1.png"
    assert manifest.images[0].size_bytes == 6000
    assert len(manifest.images[0].sha256) == 64


def test_save_asset_manifest_advances_state_only_when_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    invalid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=False)
    project = manager.save_asset_manifest(project, invalid_manifest)
    assert project.status == ProjectState.CREATED
    assert project.source_asset_manifest_id == invalid_manifest.manifest_id

    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED
    assert project.source_asset_manifest_id == valid_manifest.manifest_id


def test_export_producer_package_writes_asset_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)

    project = manager.export_producer_package(project, asset_manifest=manifest)

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert project.producer_package_dir == str(package_dir)
    assert (package_dir / "asset_manifest.json").exists()
    assert (package_dir / "manifest.json").exists()
    written = json.loads((package_dir / "asset_manifest.json").read_text())
    assert written["manifest_id"] == manifest.manifest_id
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {"asset_manifest.json"}


def test_load_shot_durations_reads_production_package(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)
    character_sheet = _make_character_sheet(plan)
    environment_sheet = _make_environment_sheet(plan)
    prompt_set = _make_prompt_set(storyboard)

    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    project = manager.save_storyboard(project, storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    project = manager.save_character_sheet(project, character_sheet)
    project = manager.save_environment_sheet(project, environment_sheet)
    project = manager.save_prompt_set(project, prompt_set)
    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone=None, audience=None, art_style=None,
    )

    durations = manager.load_shot_durations(project)

    assert len(durations) == 1
    assert durations[0].scene_id == 1
    assert durations[0].shot_id == 1
    assert durations[0].duration_seconds == 15


def test_save_timeline_does_not_advance_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED

    timeline = Timeline(source_asset_manifest_id=valid_manifest.manifest_id)
    project = manager.save_timeline(project, timeline)

    assert project.status == ProjectState.MEDIA_IMPORTED  # unchanged - Timeline alone isn't EDIT_PLAN_READY
    assert project.source_timeline_id == timeline.timeline_id


def test_export_producer_package_writes_timeline_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(
        source_asset_manifest_id=manifest.manifest_id,
        clips=[TimelineClip(
            scene_id=1, shot_id=1, asset_path="/i/s1s1.png", asset_type="image",
            duration_seconds=5, start_time=0, end_time=5,
        )],
        total_duration_seconds=5,
    )

    project = manager.export_producer_package(project, asset_manifest=manifest, timeline=timeline)

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "timeline_plan.json").exists()
    written = json.loads((package_dir / "timeline_plan.json").read_text())
    assert written["timeline_id"] == timeline.timeline_id
    assert written["total_duration_seconds"] == 5
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {"asset_manifest.json", "timeline_plan.json"}


def test_load_narration_paragraphs_splits_production_package_text(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)
    character_sheet = _make_character_sheet(plan)
    environment_sheet = _make_environment_sheet(plan)
    prompt_set = _make_prompt_set(storyboard)
    voice_script = VoiceScript(
        source_plan_id=plan.plan_id,
        lines=[NarrationLine(scene_id=1, narration_text="Mira stands at the forest edge.")],
    )

    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    project = manager.save_storyboard(project, storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    project = manager.save_character_sheet(project, character_sheet)
    project = manager.save_environment_sheet(project, environment_sheet)
    project = manager.save_prompt_set(project, prompt_set)
    project = manager.save_voice_script(project, voice_script)
    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        voice_script=voice_script, tone=None, audience=None, art_style=None,
    )

    paragraphs = manager.load_narration_paragraphs(project)

    assert paragraphs == ["Mira stands at the forest edge."]


def test_load_narration_paragraphs_returns_empty_when_voice_script_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)
    character_sheet = _make_character_sheet(plan)
    environment_sheet = _make_environment_sheet(plan)
    prompt_set = _make_prompt_set(storyboard)

    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    project = manager.save_storyboard(project, storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    project = manager.save_character_sheet(project, character_sheet)
    project = manager.save_environment_sheet(project, environment_sheet)
    project = manager.save_prompt_set(project, prompt_set)
    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone=None, audience=None, art_style=None,
    )

    paragraphs = manager.load_narration_paragraphs(project)

    assert paragraphs == []


def test_save_subtitle_plan_does_not_advance_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED

    subtitle_plan = SubtitlePlan(source_timeline_id="tl-1")
    project = manager.save_subtitle_plan(project, subtitle_plan)

    assert project.status == ProjectState.MEDIA_IMPORTED  # unchanged - Subtitles alone isn't EDIT_PLAN_READY
    assert project.source_subtitle_plan_id == subtitle_plan.subtitle_plan_id


def test_export_producer_package_writes_subtitle_plan_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(source_asset_manifest_id=manifest.manifest_id, total_duration_seconds=5)
    subtitle_plan = SubtitlePlan(
        source_timeline_id=timeline.timeline_id,
        cues=[SubtitleCue(sequence_index=1, scene_id=1, text="Mira stands.", start_time=0, end_time=5)],
        total_duration_seconds=5,
    )

    project = manager.export_producer_package(
        project, asset_manifest=manifest, timeline=timeline, subtitle_plan=subtitle_plan
    )

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "subtitle_plan.json").exists()
    written = json.loads((package_dir / "subtitle_plan.json").read_text())
    assert written["subtitle_plan_id"] == subtitle_plan.subtitle_plan_id
    assert written["cues"][0]["text"] == "Mira stands."
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {
        "asset_manifest.json", "timeline_plan.json", "subtitle_plan.json",
    }


def test_load_scene_moods_reads_production_package(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)
    character_sheet = _make_character_sheet(plan)
    environment_sheet = _make_environment_sheet(plan)
    prompt_set = _make_prompt_set(storyboard)

    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    project = manager.save_storyboard(project, storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    project = manager.save_character_sheet(project, character_sheet)
    project = manager.save_environment_sheet(project, environment_sheet)
    project = manager.save_prompt_set(project, prompt_set)
    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone=None, audience=None, art_style=None,
    )

    moods = manager.load_scene_moods(project)

    assert len(moods) == 1
    assert moods[0].scene_id == 1
    assert moods[0].mood == "hopeful"


def test_save_music_plan_does_not_advance_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED

    music_plan = MusicPlan(source_timeline_id="tl-1")
    project = manager.save_music_plan(project, music_plan)

    assert project.status == ProjectState.MEDIA_IMPORTED  # unchanged - Music Planning alone isn't EDIT_PLAN_READY
    assert project.source_music_plan_id == music_plan.music_plan_id


def test_export_producer_package_writes_music_plan_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(source_asset_manifest_id=manifest.manifest_id, total_duration_seconds=5)
    music_plan = MusicPlan(
        source_timeline_id=timeline.timeline_id,
        cues=[],
        total_duration_seconds=5,
    )

    project = manager.export_producer_package(
        project, asset_manifest=manifest, timeline=timeline, music_plan=music_plan
    )

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "music_plan.json").exists()
    written = json.loads((package_dir / "music_plan.json").read_text())
    assert written["music_plan_id"] == music_plan.music_plan_id
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {
        "asset_manifest.json", "timeline_plan.json", "music_plan.json",
    }


def test_load_production_plan_roundtrips_from_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    project = manager.create_project()
    project = manager.save_story_plan(project, plan)

    loaded = manager.load_production_plan(project)

    assert loaded.plan_id == plan.plan_id
    assert loaded.title == "Test"
    assert loaded.characters[0].role == "protagonist"


def test_load_character_sheet_roundtrips_from_legacy_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    character_sheet = _make_character_sheet(plan)
    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    project = manager.save_character_sheet(project, character_sheet)

    loaded = manager.load_character_sheet(project)

    assert loaded.sheet_id == character_sheet.sheet_id
    assert loaded.character_profiles[0].name == "Mira"
    assert loaded.character_profiles[0].reference_prompt.startswith("A lean young woman")


def test_save_editing_plan_does_not_advance_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED

    editing_plan = EditingPlan(source_timeline_id="tl-1")
    project = manager.save_editing_plan(project, editing_plan)

    assert project.status == ProjectState.MEDIA_IMPORTED  # unchanged - Editing Planning alone isn't EDIT_PLAN_READY
    assert project.source_editing_plan_id == editing_plan.editing_plan_id


def test_export_producer_package_writes_editing_plan_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(source_asset_manifest_id=manifest.manifest_id, total_duration_seconds=5)
    editing_plan = EditingPlan(
        source_timeline_id=timeline.timeline_id,
        segments=[],
        total_duration_seconds=5,
    )

    project = manager.export_producer_package(
        project, asset_manifest=manifest, timeline=timeline, editing_plan=editing_plan
    )

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "editing_plan.json").exists()
    written = json.loads((package_dir / "editing_plan.json").read_text())
    assert written["editing_plan_id"] == editing_plan.editing_plan_id
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {
        "asset_manifest.json", "timeline_plan.json", "editing_plan.json",
    }


def test_save_thumbnail_plan_does_not_advance_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED

    thumbnail_plan = ThumbnailPlan(source_editing_plan_id="ep-1")
    project = manager.save_thumbnail_plan(project, thumbnail_plan)

    assert project.status == ProjectState.MEDIA_IMPORTED  # unchanged - Thumbnail Planning alone isn't EDIT_PLAN_READY
    assert project.source_thumbnail_plan_id == thumbnail_plan.thumbnail_plan_id


def test_export_producer_package_writes_thumbnail_plan_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(source_asset_manifest_id=manifest.manifest_id, total_duration_seconds=5)
    thumbnail_plan = ThumbnailPlan(source_editing_plan_id="ep-1", variants=[])

    project = manager.export_producer_package(
        project, asset_manifest=manifest, timeline=timeline, thumbnail_plan=thumbnail_plan
    )

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "thumbnail_plan.json").exists()
    written = json.loads((package_dir / "thumbnail_plan.json").read_text())
    assert written["thumbnail_plan_id"] == thumbnail_plan.thumbnail_plan_id
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {
        "asset_manifest.json", "timeline_plan.json", "thumbnail_plan.json",
    }


def _make_publishing_plan():
    return PublishingPlan(
        source_editing_plan_id="ep-1",
        source_thumbnail_plan_id="tp-1",
        canonical=PublishingMetadata(
            title="Test", description="A test story.", keywords=["test"], hashtags=["#Test"],
            category="Education", language="en",
        ),
        youtube=YouTubeMetadata(
            title="Test", description="A test story.", tags=["test"], category="Education",
            default_language="en", playlist="Test Stories", visibility="private",
        ),
    )


def test_load_package_metadata_reads_production_package(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)
    character_sheet = _make_character_sheet(plan)
    environment_sheet = _make_environment_sheet(plan)
    prompt_set = _make_prompt_set(storyboard)

    project = manager.create_project()
    project = manager.save_story_plan(project, plan)
    project = manager.save_storyboard(project, storyboard)
    project = manager.save_shot_plan(project, shot_plan)
    project = manager.save_camera_plan(project, camera_plan)
    project = manager.save_character_sheet(project, character_sheet)
    project = manager.save_environment_sheet(project, environment_sheet)
    project = manager.save_prompt_set(project, prompt_set)
    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        tone="uplifting", audience="young children", art_style=None,
    )

    metadata = manager.load_package_metadata(project)

    assert metadata["audience"] == "young children"
    assert metadata["tone"] == "uplifting"


def test_save_publishing_metadata_advances_to_edit_plan_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    valid_manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    project = manager.save_asset_manifest(project, valid_manifest)
    assert project.status == ProjectState.MEDIA_IMPORTED

    publishing_plan = _make_publishing_plan()
    project = manager.save_publishing_metadata(project, publishing_plan)

    # Publishing Metadata is the sixth/last planning sub-stage - THIS is the advance to EDIT_PLAN_READY
    assert project.status == ProjectState.EDIT_PLAN_READY
    assert project.source_publishing_metadata_id == publishing_plan.publishing_plan_id


def test_export_producer_package_writes_publishing_metadata_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True)
    timeline = Timeline(source_asset_manifest_id=manifest.manifest_id, total_duration_seconds=5)
    publishing_plan = _make_publishing_plan()

    project = manager.export_producer_package(
        project, asset_manifest=manifest, timeline=timeline, publishing_plan=publishing_plan
    )

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "publishing_metadata.json").exists()
    written = json.loads((package_dir / "publishing_metadata.json").read_text())
    assert written["publishing_plan_id"] == publishing_plan.publishing_plan_id
    assert written["youtube"]["visibility"] == "private"
    manifest_index = json.loads((package_dir / "manifest.json").read_text())
    assert {f["name"] for f in manifest_index["files"]} == {
        "asset_manifest.json", "timeline_plan.json", "publishing_metadata.json",
    }

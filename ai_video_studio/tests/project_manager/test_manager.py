import json
import uuid
from pathlib import Path

import pytest

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
from shared_core.contracts.publish import (
    AuthenticationResult,
    PublishResult,
    PublishValidationCheck,
    PublishValidationReport,
    ReadyToPublishResult,
)
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata
from shared_core.contracts.render import RenderResult, RenderValidationCheck, RenderValidationReport
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


def test_scan_media_reuses_cached_hash_for_unchanged_file(tmp_path, monkeypatch):
    """Milestone W10: a second scan of a file whose size/mtime haven't
    changed must not re-read its bytes - the whole point of the cache added
    to _scan_subdir. Asserted indirectly (no read_bytes call) so the test
    exercises the real code path rather than mocking internals."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    images_dir = manager.get_media_dir(project) / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "scene_1_shot_1.png"
    image_path.write_bytes(b"0" * 6000)

    first = manager.scan_media(project)
    original_read_bytes = Path.read_bytes
    calls = []

    def spy_read_bytes(self, *args, **kwargs):
        calls.append(self)
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    second = manager.scan_media(project)

    assert calls == []
    assert second.images[0].sha256 == first.images[0].sha256
    assert second.images[0].size_bytes == first.images[0].size_bytes


def test_scan_media_rehashes_when_file_content_changes(tmp_path, monkeypatch):
    """The cache must not serve a stale hash once a file is genuinely
    overwritten (size and/or mtime change)."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    images_dir = manager.get_media_dir(project) / "images"
    images_dir.mkdir(parents=True)
    image_path = images_dir / "scene_1_shot_1.png"
    image_path.write_bytes(b"0" * 6000)

    first = manager.scan_media(project)

    image_path.write_bytes(b"1" * 7000)
    second = manager.scan_media(project)

    assert second.images[0].size_bytes == 7000
    assert second.images[0].sha256 != first.images[0].sha256


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


def test_get_render_dir_is_project_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    render_dir = manager.get_render_dir(project)

    assert render_dir == tmp_path / "projects" / project.project_id / "renders"
    assert not render_dir.exists()  # location handed out, not created


def test_load_producer_package_contracts_roundtrip(tmp_path, monkeypatch):
    from shared_core.contracts.editing_plan import EditingPlan
    from shared_core.contracts.music_plan import MusicPlan
    from shared_core.contracts.subtitle import SubtitlePlan

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manifest = ValidatedAssetManifest(source_prompt_set_id="abc", is_valid=True, narration_audio_path="/a/v.wav")
    timeline = Timeline(source_asset_manifest_id=manifest.manifest_id, total_duration_seconds=5)
    subtitle_plan = SubtitlePlan(source_timeline_id=timeline.timeline_id)
    music_plan = MusicPlan(source_timeline_id=timeline.timeline_id)
    editing_plan = EditingPlan(
        source_timeline_id=timeline.timeline_id,
        source_subtitle_plan_id=subtitle_plan.subtitle_plan_id,
        source_music_plan_id=music_plan.music_plan_id,
        total_duration_seconds=5,
    )

    project = manager.export_producer_package(
        project, asset_manifest=manifest, timeline=timeline, subtitle_plan=subtitle_plan,
        music_plan=music_plan, editing_plan=editing_plan,
    )

    assert manager.load_asset_manifest(project).manifest_id == manifest.manifest_id
    assert manager.load_editing_plan(project).editing_plan_id == editing_plan.editing_plan_id
    assert manager.load_producer_timeline(project).timeline_id == timeline.timeline_id
    assert manager.load_subtitle_plan(project).subtitle_plan_id == subtitle_plan.subtitle_plan_id
    assert manager.load_music_plan(project).music_plan_id == music_plan.music_plan_id


def test_load_editing_plan_without_producer_package_raises(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()  # no producer package yet

    with pytest.raises(ValueError, match="no Producer Package"):
        manager.load_editing_plan(project)


def _successful_render_result(output_path="/renders/video.mp4"):
    return RenderResult(success=True, dry_run=False, output_path=output_path, exit_code=0, duration_seconds=5.0)


def _failed_render_result():
    return RenderResult(
        success=False, dry_run=False, exit_code=1, error="ffmpeg exited with code 1", error_type="ffmpeg_failed",
    )


def _passing_validation_report(output_path="/renders/video.mp4"):
    return RenderValidationReport(
        is_valid=True,
        checks=[RenderValidationCheck(name="duration", passed=True, expected="20.0s", actual="20.0s")],
        output_path=output_path,
    )


def _failing_validation_report(output_path="/renders/video.mp4"):
    return RenderValidationReport(
        is_valid=False,
        checks=[RenderValidationCheck(name="duration", passed=False, expected="20.0s", actual="1.0s")],
        output_path=output_path,
    )


def test_save_render_result_advances_to_video_rendered_only_when_both_succeed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    render_result = _successful_render_result()
    project = manager.save_render_result(
        project, render_result=render_result, validation_report=_passing_validation_report()
    )

    assert project.status == ProjectState.VIDEO_RENDERED
    assert project.rendered_video_path == render_result.output_path


def test_save_render_result_does_not_advance_when_validation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    original_status = project.status

    project = manager.save_render_result(
        project, render_result=_successful_render_result(), validation_report=_failing_validation_report()
    )

    assert project.status == original_status  # unchanged
    assert project.rendered_video_path is None


def test_save_render_result_does_not_advance_when_execution_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    original_status = project.status

    project = manager.save_render_result(project, render_result=_failed_render_result(), validation_report=None)

    assert project.status == original_status
    assert project.rendered_video_path is None


def test_save_render_result_writes_both_reports_on_full_success(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manager.save_render_result(
        project, render_result=_successful_render_result(), validation_report=_passing_validation_report()
    )

    render_dir = tmp_path / "projects" / project.project_id / "renders"
    assert (render_dir / "render_report.json").exists()
    assert (render_dir / "render_validation.json").exists()
    report = json.loads((render_dir / "render_report.json").read_text())
    validation = json.loads((render_dir / "render_validation.json").read_text())
    assert report["success"] is True
    assert validation["is_valid"] is True


def test_save_render_result_writes_only_report_when_validation_not_run(tmp_path, monkeypatch):
    """execution-process diagnostics (render_report.json) and output-quality
    verification (render_validation.json) are kept as two separate files -
    a failed execution has nothing to validate, so only the former exists."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manager.save_render_result(project, render_result=_failed_render_result(), validation_report=None)

    render_dir = tmp_path / "projects" / project.project_id / "renders"
    assert (render_dir / "render_report.json").exists()
    assert not (render_dir / "render_validation.json").exists()


def _valid_publishing_metadata_json() -> str:
    plan = PublishingPlan(
        canonical=PublishingMetadata(
            title="Test Video", description="A test video.", category="Education", language="en",
        ),
        youtube=YouTubeMetadata(
            title="Test Video", description="A test video.", category="27",
            default_language="en", playlist="", visibility="private",
        ),
    )
    return plan.model_dump_json()


def test_get_publish_dir_is_project_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    assert manager.get_publish_dir(project) == tmp_path / "projects" / project.project_id / "publishing"


def test_check_publish_readiness_passes_for_a_fully_ready_project(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    package_dir.mkdir(parents=True)
    (package_dir / "publishing_metadata.json").write_text(_valid_publishing_metadata_json())

    video_path = tmp_path / "projects" / project.project_id / "renders" / "video.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"fake mp4 bytes")

    ready_project = project.model_copy(
        update={
            "status": ProjectState.VIDEO_RENDERED,
            "rendered_video_path": str(video_path),
            "producer_package_dir": str(package_dir),
        }
    )

    report = manager.check_publish_readiness(ready_project, platform="youtube")

    assert report.is_valid is True
    assert report.platform == "youtube"


def test_check_publish_readiness_reports_not_ready_for_a_fresh_project(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    report = manager.check_publish_readiness(project, platform="youtube")

    assert report.is_valid is False
    assert any(not c.passed for c in report.checks)


def test_check_publish_readiness_writes_publish_validation_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manager.check_publish_readiness(project, platform="youtube")

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    validation_file = publish_dir / "publish_validation.json"
    assert validation_file.exists()
    saved = json.loads(validation_file.read_text())
    assert saved["is_valid"] is False
    assert saved["platform"] == "youtube"


def test_check_publish_readiness_never_modifies_persisted_project_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    original_project_json = (tmp_path / "projects" / project.project_id / "project.json").read_text()

    elevated = project.model_copy(update={"status": ProjectState.VIDEO_RENDERED, "rendered_video_path": "/tmp/video.mp4"})
    manager.check_publish_readiness(elevated, platform="youtube")

    persisted = (tmp_path / "projects" / project.project_id / "project.json").read_text()
    assert persisted == original_project_json
    assert json.loads(persisted)["status"] == "CREATED"


def test_build_publish_readiness_request_reflects_project_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    elevated = project.model_copy(
        update={
            "status": ProjectState.VIDEO_RENDERED,
            "rendered_video_path": "/tmp/video.mp4",
            "producer_package_dir": str(tmp_path / "producer-package"),
        }
    )

    request = manager.build_publish_readiness_request(elevated, platform="youtube")

    assert request.project_status == "VIDEO_RENDERED"
    assert request.video_path == "/tmp/video.mp4"
    assert request.publishing_metadata_path == str(tmp_path / "producer-package" / "publishing_metadata.json")
    assert request.platform == "youtube"
    assert request.output_dir == str(manager.get_publish_dir(elevated))


def test_build_publish_readiness_request_handles_project_with_no_producer_package_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    request = manager.build_publish_readiness_request(project, platform="youtube")

    assert request.video_path == ""
    assert request.publishing_metadata_path == ""


def test_load_publishing_plan_roundtrips_from_producer_package(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    package_dir.mkdir(parents=True)
    plan = PublishingPlan(
        canonical=PublishingMetadata(title="T", description="D", category="Education", language="en"),
        youtube=YouTubeMetadata(
            title="T", description="D", category="27", default_language="en", playlist="", visibility="private"
        ),
    )
    (package_dir / "publishing_metadata.json").write_text(plan.model_dump_json())
    with_package = project.model_copy(update={"producer_package_dir": str(package_dir)})

    loaded = manager.load_publishing_plan(with_package)

    assert loaded.canonical.title == "T"
    assert loaded.youtube.visibility == "private"


def test_load_publishing_plan_raises_when_no_producer_package_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    try:
        manager.load_publishing_plan(project)
        assert False, "expected ValueError"
    except ValueError:
        pass


def _ready_to_publish_result(*, ready=True) -> ReadyToPublishResult:
    passing_check = PublishValidationCheck(name="project_state", passed=True, expected="VIDEO_RENDERED", actual="VIDEO_RENDERED")
    failing_check = PublishValidationCheck(name="project_state", passed=False, expected="VIDEO_RENDERED", actual="EDIT_PLAN_READY")
    readiness = PublishValidationReport(is_valid=ready, checks=[passing_check if ready else failing_check], platform="youtube")
    credentials = PublishValidationReport(is_valid=ready, checks=[passing_check if ready else failing_check], platform="youtube")
    authentication = (
        AuthenticationResult(success=True, platform="youtube", account_label="My Channel")
        if ready
        else AuthenticationResult(success=False, platform="youtube", error="boom", error_type="expired_token")
    )
    return ReadyToPublishResult(
        platform="youtube",
        dry_run=True,
        readiness=readiness,
        credentials=credentials,
        authentication=authentication,
        ready_to_publish=ready,
        request=None,
    )


def test_save_publish_report_writes_publish_report_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manager.save_publish_report(project, _ready_to_publish_result(ready=True))

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    report_file = publish_dir / "publish_report.json"
    assert report_file.exists()
    saved = json.loads(report_file.read_text())
    assert saved["ready_to_publish"] is True
    assert saved["platform"] == "youtube"
    assert saved["authentication"]["success"] is True
    assert saved["authentication"]["account_label"] == "My Channel"


def test_save_publish_report_persists_failed_readiness_too(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manager.save_publish_report(project, _ready_to_publish_result(ready=False))

    saved = json.loads((tmp_path / "projects" / project.project_id / "publishing" / "publish_report.json").read_text())
    assert saved["ready_to_publish"] is False
    assert saved["authentication"]["error_type"] == "expired_token"


def test_save_publish_report_returns_project_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    returned = manager.save_publish_report(project, _ready_to_publish_result(ready=True))

    assert returned == project
    assert returned.status == ProjectState.CREATED  # unchanged, even though ready_to_publish=True


def test_save_publish_report_never_writes_or_modifies_project_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    original_project_json = (tmp_path / "projects" / project.project_id / "project.json").read_text()

    manager.save_publish_report(project, _ready_to_publish_result(ready=True))

    persisted = (tmp_path / "projects" / project.project_id / "project.json").read_text()
    assert persisted == original_project_json


def test_save_publish_report_does_not_overwrite_publish_validation_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manager.check_publish_readiness(project, platform="youtube")  # writes publish_validation.json

    manager.save_publish_report(project, _ready_to_publish_result(ready=True))

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    assert (publish_dir / "publish_validation.json").exists()
    assert (publish_dir / "publish_report.json").exists()
    # the two files are independently written and don't clobber each other
    validation = json.loads((publish_dir / "publish_validation.json").read_text())
    report = json.loads((publish_dir / "publish_report.json").read_text())
    assert "checks" in validation
    assert "ready_to_publish" in report and "checks" not in report


def test_save_upload_result_writes_upload_report_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid1", bytes_uploaded=500, total_bytes=500)

    manager.save_upload_result(project, upload_result)

    saved = json.loads((tmp_path / "projects" / project.project_id / "publishing" / "upload_report.json").read_text())
    assert saved["success"] is True
    assert saved["external_video_id"] == "vid1"


def test_save_upload_result_writes_verification_only_when_provided(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    upload_result = PublishResult(success=False, platform="youtube", error="boom", error_type="interrupted")

    manager.save_upload_result(project, upload_result)

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    assert (publish_dir / "upload_report.json").exists()
    assert not (publish_dir / "upload_verification.json").exists()


def test_save_upload_result_writes_both_files_when_verification_given(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid1")
    verification = PublishValidationReport(
        is_valid=True, platform="youtube",
        checks=[PublishValidationCheck(name="video_retrievable", passed=True, expected="x", actual="x")],
    )

    manager.save_upload_result(project, upload_result, verification=verification)

    publish_dir = tmp_path / "projects" / project.project_id / "publishing"
    assert (publish_dir / "upload_report.json").exists()
    assert (publish_dir / "upload_verification.json").exists()
    saved_verification = json.loads((publish_dir / "upload_verification.json").read_text())
    assert saved_verification["is_valid"] is True


def test_save_upload_result_never_modifies_project_state_even_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    original_project_json = (tmp_path / "projects" / project.project_id / "project.json").read_text()
    upload_result = PublishResult(success=True, platform="youtube", external_video_id="vid1")
    verification = PublishValidationReport(is_valid=True, platform="youtube", checks=[])

    returned = manager.save_upload_result(project, upload_result, verification=verification)

    persisted = (tmp_path / "projects" / project.project_id / "project.json").read_text()
    assert persisted == original_project_json
    assert returned.status == ProjectState.CREATED
    assert json.loads(persisted)["status"] == "CREATED"


def test_list_projects_empty_when_output_dir_has_no_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    assert manager.list_projects() == []


def test_list_projects_returns_all_created_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    first = manager.create_project()
    second = manager.create_project()

    projects = manager.list_projects()

    assert {p.project_id for p in projects} == {first.project_id, second.project_id}


def test_list_projects_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    older = manager.create_project()
    older = manager._advance(older, created_at=older.created_at.replace(year=older.created_at.year - 1))
    newer = manager.create_project()

    projects = manager.list_projects()

    assert [p.project_id for p in projects] == [newer.project_id, older.project_id]


def test_list_projects_skips_directories_without_project_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    valid = manager.create_project()
    (tmp_path / "projects" / "not-a-real-project").mkdir(parents=True)

    projects = manager.list_projects()

    assert [p.project_id for p in projects] == [valid.project_id]


def test_delete_project_removes_project_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    project_dir = tmp_path / "projects" / project.project_id
    assert project_dir.exists()

    manager.delete_project(project.project_id)

    assert not project_dir.exists()


def test_delete_project_unknown_id_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()

    with pytest.raises(FileNotFoundError):
        manager.delete_project(str(uuid.uuid4()))


@pytest.mark.parametrize("filename,subdir", [
    ("shot1.png", "images"),
    ("shot1.JPG", "images"),
    ("shot1.jpeg", "images"),
    ("clip1.mp4", "video"),
    ("clip1.mov", "video"),
    ("narration.wav", "audio"),
    ("narration.mp3", "audio"),
    ("narration.m4a", "audio"),
])
def test_save_uploaded_media_routes_by_extension(tmp_path, monkeypatch, filename, subdir):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    saved_path = manager.save_uploaded_media(project, filename, b"content")

    expected_path = tmp_path / "projects" / project.project_id / "media" / subdir / filename
    assert saved_path == expected_path
    assert expected_path.read_bytes() == b"content"


def test_save_uploaded_media_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    with pytest.raises(ValueError):
        manager.save_uploaded_media(project, "malware.exe", b"content")


def test_save_uploaded_media_rejects_extensionless_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    with pytest.raises(ValueError):
        manager.save_uploaded_media(project, "noextension", b"content")


def test_save_uploaded_media_strips_path_traversal_from_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    saved_path = manager.save_uploaded_media(project, "../../evil.png", b"content")

    expected_path = tmp_path / "projects" / project.project_id / "media" / "images" / "evil.png"
    assert saved_path == expected_path
    assert saved_path.is_relative_to(tmp_path / "projects" / project.project_id / "media")


def test_save_uploaded_media_is_visible_to_scan_media(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    manager.save_uploaded_media(project, "shot1.png", b"x" * 100)
    manager.save_uploaded_media(project, "clip1.mp4", b"x" * 100)
    manager.save_uploaded_media(project, "narration.wav", b"x" * 100)

    manifest = manager.scan_media(project)

    assert [f.filename for f in manifest.images] == ["shot1.png"]
    assert [f.filename for f in manifest.videos] == ["clip1.mp4"]
    assert [f.filename for f in manifest.audio] == ["narration.wav"]


def test_delete_uploaded_media_removes_file_and_is_gone_from_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    saved_path = manager.save_uploaded_media(project, "shot1.png", b"x" * 100)
    assert saved_path.exists()

    manager.delete_uploaded_media(project, "images", "shot1.png")

    assert not saved_path.exists()
    manifest = manager.scan_media(project)
    assert manifest.images == []


def test_delete_uploaded_media_raises_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    with pytest.raises(FileNotFoundError):
        manager.delete_uploaded_media(project, "images", "nope.png")


def test_delete_uploaded_media_rejects_unknown_category(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    with pytest.raises(ValueError):
        manager.delete_uploaded_media(project, "documents", "shot1.png")


def test_delete_uploaded_media_strips_path_traversal_from_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manager.save_uploaded_media(project, "evil.png", b"content")

    manager.delete_uploaded_media(project, "images", "../../evil.png")

    assert not (manager.get_media_dir(project) / "images" / "evil.png").exists()


def test_delete_uploaded_media_only_removes_the_named_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    manager.save_uploaded_media(project, "shot1.png", b"x" * 100)
    manager.save_uploaded_media(project, "shot2.png", b"y" * 100)

    manager.delete_uploaded_media(project, "images", "shot1.png")

    manifest = manager.scan_media(project)
    assert [f.filename for f in manifest.images] == ["shot2.png"]


def test_load_production_package_raises_when_not_yet_generated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    with pytest.raises(ValueError):
        manager.load_production_package(project)


def test_load_production_package_returns_every_file_keyed_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()
    plan = _make_plan()
    storyboard = _make_storyboard(plan)
    shot_plan = _make_shot_plan(storyboard)
    camera_plan = _make_camera_plan(shot_plan)
    character_sheet = _make_character_sheet(plan)
    environment_sheet = _make_environment_sheet(plan)
    prompt_set = _make_prompt_set(storyboard)
    research_brief = _make_research_brief()
    voice_script = _make_voice_script(plan)

    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        research_brief=research_brief, voice_script=voice_script, tone="uplifting", audience=None,
        art_style=None,
    )

    package = manager.load_production_package(project)

    assert set(package) == {
        "manifest.json", "metadata.json", "research_brief.json", "story.md", "scene_plan.json",
        "shot_plan.json", "camera_plan.json", "character_bible.json", "environment_bible.json",
        "image_prompts.json", "video_prompts.json", "voice_script.txt",
    }
    # JSON files are parsed structured content, not raw text
    assert package["character_bible.json"]["character_profiles"][0]["name"] == "Mira"
    assert package["research_brief.json"]["key_facts"] == research_brief.key_facts
    # non-JSON files come back as plain text, exactly as package_writer wrote them
    assert package["voice_script.txt"] == "Mira starts her journey at dawn."
    assert package["story.md"].startswith("# Test")
    # manifest.json's own content is included, matching what's really on disk
    assert package["manifest.json"]["package_id"] == project.project_id
    # no raw filesystem path anywhere in the response
    assert project.production_package_dir not in json.dumps(package)


def test_load_producer_package_raises_when_not_yet_generated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()

    with pytest.raises(ValueError):
        manager.load_producer_package(project)


def test_load_producer_package_returns_every_file_keyed_by_name(tmp_path, monkeypatch):
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

    package = manager.load_producer_package(project)

    assert set(package) == {"manifest.json", "asset_manifest.json", "timeline_plan.json"}
    assert package["asset_manifest.json"]["manifest_id"] == manifest.manifest_id
    assert package["timeline_plan.json"]["timeline_id"] == timeline.timeline_id
    assert package["manifest.json"]["package_id"] == project.project_id
    assert project.producer_package_dir not in json.dumps(package)

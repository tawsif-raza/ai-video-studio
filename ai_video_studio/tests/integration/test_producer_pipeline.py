import json
import sys

import pytest

import producer_app as producer_app_module
from agents.character_planner.contract import CharacterSheet
from agents.character_planner.schema import CharacterVisualProfile
from agents.environment_planner.contract import EnvironmentSheet
from agents.environment_planner.schema import EnvironmentProfile
from agents.prompt_generator.contract import PromptSet, ShotPrompt
from agents.scene_planner.contract import Storyboard
from agents.scene_planner.schema import ScenePlan, ShotBrief
from agents.story_planner.contract import ProductionPlan
from agents.story_planner.schema import CharacterBrief, SceneBrief
from agents.voice_script.contract import VoiceScript
from agents.voice_script.schema import NarrationLine
from config import settings
from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from shared_core.contracts.camera_plan import CameraPlan, CameraScenePlan, CameraShot
from shared_core.contracts.shot_plan import ShotItem, ShotPlan, ShotScenePlan


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
                        shot_id=1, description="Mira stands at the forest edge",
                        characters_in_shot=["Mira"], duration_seconds=15,
                    ),
                    ShotBrief(
                        shot_id=2, description="Mira looks determined",
                        characters_in_shot=["Mira"], duration_seconds=15,
                    ),
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
                    ShotItem(shot_id=1, description="Mira stands at the forest edge",
                             characters_in_shot=["Mira"], duration_seconds=15),
                    ShotItem(shot_id=2, description="Mira looks determined",
                             characters_in_shot=["Mira"], duration_seconds=15),
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
                shots=[
                    CameraShot(shot_id=1, camera_angle="wide shot", camera_movement="static"),
                    CameraShot(shot_id=2, camera_angle="close-up", camera_movement="slow zoom in"),
                ],
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
            ),
            ShotPrompt(
                scene_id=1, shot_id=2, duration_seconds=15,
                image_prompt="Close-up of Mira's determined face, cinematic realism, warm lighting throughout.",
                video_motion_prompt="Slow zoom in on Mira's face as her expression firms with resolve.",
            ),
        ],
    )


def _make_voice_script(plan):
    return VoiceScript(
        source_plan_id=plan.plan_id,
        lines=[NarrationLine(
            scene_id=1,
            narration_text="Mira stands at the misty forest edge. She looks determined.",
        )],
    )


def _build_package_ready_project(tmp_path, monkeypatch):
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
    voice_script = _make_voice_script(plan)
    project = manager.save_voice_script(project, voice_script)

    project = manager.export_production_package(
        project, plan=plan, storyboard=storyboard, shot_plan=shot_plan, camera_plan=camera_plan,
        character_sheet=character_sheet, environment_sheet=environment_sheet, prompt_set=prompt_set,
        voice_script=voice_script, tone="uplifting", audience=None, art_style=None,
    )
    assert project.status == ProjectState.PACKAGE_READY
    return manager, project


def _write_media(manager, project, *, images=(), videos=(), audio=()):
    media_dir = manager.get_media_dir(project)
    if images:
        (media_dir / "images").mkdir(parents=True, exist_ok=True)
        for name, content in images:
            (media_dir / "images" / name).write_bytes(content)
    if videos:
        (media_dir / "video").mkdir(parents=True, exist_ok=True)
        for name, content in videos:
            (media_dir / "video" / name).write_bytes(content)
    if audio:
        (media_dir / "audio").mkdir(parents=True, exist_ok=True)
        for name, content in audio:
            (media_dir / "audio" / name).write_bytes(content)


def _run_producer_app(monkeypatch, project_id):
    monkeypatch.setattr(sys, "argv", ["producer_app.py", "--project-id", project_id])
    with pytest.raises(SystemExit) as exc_info:
        producer_app_module.main()
    return exc_info.value.code


def test_complete_media_advances_to_media_imported_and_builds_timeline_and_subtitles(tmp_path, monkeypatch, capsys):
    manager, project = _build_package_ready_project(tmp_path, monkeypatch)
    _write_media(
        manager, project,
        images=[("scene_1_shot_1.png", b"0" * 6000), ("scene_1_shot_2.png", b"1" * 6000)],
        audio=[("voice_script.wav", b"2" * 6000)],
    )

    exit_code = _run_producer_app(monkeypatch, project.project_id)

    assert exit_code == 0
    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.EDIT_PLAN_READY  # all six planning sub-stages done
    assert reloaded.source_asset_manifest_id is not None
    assert reloaded.source_timeline_id is not None
    assert reloaded.source_subtitle_plan_id is not None
    assert reloaded.source_music_plan_id is not None
    assert reloaded.source_editing_plan_id is not None
    assert reloaded.source_thumbnail_plan_id is not None
    assert reloaded.source_publishing_metadata_id is not None

    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    assert (package_dir / "asset_manifest.json").exists()
    written = json.loads((package_dir / "asset_manifest.json").read_text())
    assert written["is_valid"] is True

    assert (package_dir / "timeline_plan.json").exists()
    timeline_written = json.loads((package_dir / "timeline_plan.json").read_text())
    clips = sorted(timeline_written["clips"], key=lambda c: (c["scene_id"], c["shot_id"]))
    assert [c["shot_id"] for c in clips] == [1, 2]
    assert clips[0]["start_time"] == 0
    assert clips[0]["end_time"] == 15
    assert clips[1]["start_time"] == 15
    assert clips[1]["end_time"] == 30
    assert timeline_written["total_duration_seconds"] == 30
    assert len(timeline_written["voice_segments"]) == 1
    assert timeline_written["voice_segments"][0]["scene_id"] == 1
    assert timeline_written["voice_segments"][0]["end_time"] == 30

    assert (package_dir / "subtitle_plan.json").exists()
    subtitle_written = json.loads((package_dir / "subtitle_plan.json").read_text())
    assert subtitle_written["source_timeline_id"] == timeline_written["timeline_id"]
    cues = subtitle_written["cues"]
    assert len(cues) == 2  # two sentences in the narration text
    assert [c["sequence_index"] for c in cues] == [1, 2]
    assert cues[0]["text"] == "Mira stands at the misty forest edge."
    assert cues[1]["text"] == "She looks determined."
    assert cues[0]["start_time"] == 0
    assert cues[-1]["end_time"] == 30
    for prev, nxt in zip(cues, cues[1:]):
        assert prev["end_time"] == nxt["start_time"]

    assert (package_dir / "music_plan.json").exists()
    music_written = json.loads((package_dir / "music_plan.json").read_text())
    assert music_written["source_timeline_id"] == timeline_written["timeline_id"]
    music_cues = music_written["cues"]
    assert len(music_cues) == 1
    assert music_cues[0]["scene_id"] == 1
    assert music_cues[0]["mood"] == "uplifting"
    assert music_cues[0]["tempo"] == "medium"
    assert music_cues[0]["is_silent"] is False
    assert len(music_cues[0]["duck_windows"]) == 2  # one per subtitle cue in the scene

    assert (package_dir / "editing_plan.json").exists()
    editing_written = json.loads((package_dir / "editing_plan.json").read_text())
    assert editing_written["source_timeline_id"] == timeline_written["timeline_id"]
    assert editing_written["source_subtitle_plan_id"] == subtitle_written["subtitle_plan_id"]
    assert editing_written["source_music_plan_id"] == music_written["music_plan_id"]
    segments = sorted(editing_written["segments"], key=lambda s: s["shot_id"])
    assert len(segments) == 2
    assert segments[0]["asset_path"] == clips[0]["asset_path"]
    assert segments[0]["asset_type"] == "image"
    assert segments[0]["effects_placeholders"] == ["ken_burns"]
    assert segments[0]["music_cue_scene_id"] == 1
    assert segments[0]["transition_in"] == "fade_from_black"
    assert segments[0]["transition_out"] == "cut"  # same scene, next shot
    assert segments[1]["transition_out"] == "fade_to_black"
    # cue 1 spans [0, ~19.1) (overlaps both shots), cue 2 spans [~19.1, 30) (overlaps shot 2 only)
    assert segments[0]["subtitle_cue_indices"] == [1]
    assert segments[1]["subtitle_cue_indices"] == [1, 2]
    assert editing_written["total_duration_seconds"] == 30

    assert (package_dir / "thumbnail_plan.json").exists()
    thumbnail_written = json.loads((package_dir / "thumbnail_plan.json").read_text())
    assert thumbnail_written["source_editing_plan_id"] == editing_written["editing_plan_id"]
    variants = thumbnail_written["variants"]
    assert len(variants) == 1
    v = variants[0]
    assert v["focal_subject"] == "Mira"  # protagonist from the plan
    assert v["emotion"] == "triumphant"  # "uplifting" tone
    assert "Mira" in v["image_prompt"]
    assert "Test" in v["image_prompt"]  # story title
    assert len(v["text_safe_areas"]) >= 1

    assert (package_dir / "publishing_metadata.json").exists()
    publishing_written = json.loads((package_dir / "publishing_metadata.json").read_text())
    assert publishing_written["source_editing_plan_id"] == editing_written["editing_plan_id"]
    assert publishing_written["source_thumbnail_plan_id"] == thumbnail_written["thumbnail_plan_id"]
    assert publishing_written["canonical"]["title"] == "Test"  # story title
    assert publishing_written["youtube"]["visibility"] == "private"
    assert publishing_written["youtube"]["default_language"] == "en"
    assert "mira" in publishing_written["canonical"]["keywords"]  # protagonist name, lowercased
    assert publishing_written["canonical"]["category"] in ("Education", "Entertainment")

    printed = json.loads(capsys.readouterr().out)
    assert printed["asset_validation"]["is_valid"] is True
    assert printed["timeline"]["total_duration_seconds"] == 30
    assert len(printed["subtitles"]["cues"]) == 2
    assert len(printed["music"]["cues"]) == 1
    assert len(printed["editing"]["segments"]) == 2
    assert len(printed["thumbnail"]["variants"]) == 1
    assert printed["publishing"]["youtube"]["visibility"] == "private"


def test_missing_shot_within_tolerance_still_advances(tmp_path, monkeypatch, capsys):
    # Release milestone: a shot or two not yet generated no longer blocks
    # Producer Studio outright - Asset Validation tolerates up to
    # MAX_TOLERATED_MISSING_SHOTS missing shots (the Execution Engine renders
    # a black frame for each), so the pipeline still completes end to end.
    manager, project = _build_package_ready_project(tmp_path, monkeypatch)
    _write_media(
        manager, project,
        images=[("scene_1_shot_1.png", b"0" * 6000)],  # shot 2 missing entirely - within tolerance
        audio=[("voice_script.wav", b"2" * 6000)],
    )

    exit_code = _run_producer_app(monkeypatch, project.project_id)

    assert exit_code == 0
    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.EDIT_PLAN_READY
    assert reloaded.source_editing_plan_id is not None

    printed = json.loads(capsys.readouterr().out)
    assert printed["asset_validation"]["is_valid"] is True
    assert printed["asset_validation"]["missing_shot_count"] == 1
    assert any("shot 2" in issue["description"] for issue in printed["asset_validation"]["issues"])
    assert len(printed["editing"]["segments"]) == 2


def test_naming_violation_still_blocks_regardless_of_missing_shot_tolerance(tmp_path, monkeypatch, capsys):
    # Missing-shot coverage is the only category Asset Validation tolerates
    # by count - a naming violation (or any other issue type) must still
    # block outright, same as before this milestone.
    manager, project = _build_package_ready_project(tmp_path, monkeypatch)
    _write_media(
        manager, project,
        images=[("scene_1_shot_1.png", b"0" * 6000), ("not_a_valid_name.png", b"1" * 6000)],
        audio=[("voice_script.wav", b"2" * 6000)],
    )

    exit_code = _run_producer_app(monkeypatch, project.project_id)

    assert exit_code == 1
    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.PACKAGE_READY  # unchanged
    assert reloaded.source_editing_plan_id is None
    assert not (tmp_path / "projects" / project.project_id / "producer-package").exists()

    printed = json.loads(capsys.readouterr().out)
    assert printed["asset_validation"]["is_valid"] is False
    assert any(issue["category"] == "naming" for issue in printed["asset_validation"]["issues"])
    assert "editing" not in printed


def test_video_only_coverage_also_valid(tmp_path, monkeypatch):
    manager, project = _build_package_ready_project(tmp_path, monkeypatch)
    _write_media(
        manager, project,
        videos=[("scene_1_shot_1.mp4", b"0" * 20000), ("scene_1_shot_2.mp4", b"1" * 20000)],
        audio=[("voice_script.mp3", b"2" * 6000)],
    )

    exit_code = _run_producer_app(monkeypatch, project.project_id)

    assert exit_code == 0
    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.EDIT_PLAN_READY
    assert reloaded.source_timeline_id is not None
    assert reloaded.source_subtitle_plan_id is not None
    assert reloaded.source_music_plan_id is not None
    assert reloaded.source_editing_plan_id is not None
    assert reloaded.source_thumbnail_plan_id is not None
    assert reloaded.source_publishing_metadata_id is not None


def test_rejects_project_not_yet_package_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()  # status stays CREATED

    exit_code = _run_producer_app(monkeypatch, project.project_id)

    assert exit_code == 1

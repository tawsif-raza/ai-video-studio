import hashlib
import json
from pathlib import Path

import pytest

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
from execution_engine.controller import ExecutionEngineController
from execution_engine.errors import ExecutionEnvironmentError, MediaAccessError, RenderInputError
from producer_studio.controller import ProducerStudioController
from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from shared_core.contracts.camera_plan import CameraPlan, CameraScenePlan, CameraShot
from shared_core.contracts.render import FFmpegInfo, ProbedMedia, RenderOptions, RenderResult
from shared_core.contracts.shot_plan import ShotItem, ShotPlan, ShotScenePlan


def _available_detector():
    return FFmpegInfo(available=True, path="/usr/bin/ffmpeg", version="6.1.1",
                      raw_version_line="ffmpeg version 6.1.1")


def _unavailable_detector():
    return FFmpegInfo(available=False)


def _fake_successful_executor(command_spec, *, ffmpeg_path, timeout_seconds):
    """Stands in for ffmpeg_executor.execute() without spawning a real
    process - writes a small real file at the spec's output path, exactly
    like a genuine successful render would leave behind."""
    output = Path(command_spec.output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"fake rendered video bytes")
    return RenderResult(success=True, dry_run=False, output_path=str(output), exit_code=0, duration_seconds=0.01)


def _fake_failing_executor(command_spec, *, ffmpeg_path, timeout_seconds):
    return RenderResult(
        success=False, dry_run=False, exit_code=1, error="ffmpeg exited with code 1",
        error_type="ffmpeg_failed", stderr_tail="fake failure",
    )


# This fixture's editing plan totals 4.0s (two 2s shots) at the default
# RenderOptions (1920x1080 @ 30fps) - these fake probes stand in for
# ffprobe_client.probe() so postflight behavior can be tested without a real
# rendered file.
def _passing_prober(path, ffprobe_path="ffprobe"):
    return ProbedMedia(
        duration_seconds=4.0, has_video_stream=True, video_width=1920, video_height=1080,
        video_fps=30.0, video_codec="h264", has_audio_stream=True, audio_codec="aac",
    )


def _wrong_duration_prober(path, ffprobe_path="ffprobe"):
    return ProbedMedia(
        duration_seconds=1.0,  # far outside postflight's tolerance of the expected 4.0s
        has_video_stream=True, video_width=1920, video_height=1080, video_fps=30.0,
        has_audio_stream=True,
    )


def _unprobeable_prober(path, ffprobe_path="ffprobe"):
    return None


def _make_plan():
    return ProductionPlan(
        title="Test", logline="A test", theme="courage", target_duration_seconds=4, tone="uplifting",
        characters=[CharacterBrief(name="Mira", role="protagonist", one_line_description="brave")],
        scenes=[SceneBrief(scene_id=1, title="Opening", summary="Mira starts", setting="Forest clearing",
                           mood="hopeful", characters_present=["Mira"], estimated_duration_seconds=4)],
        source_idea="test idea",
    )


def _make_storyboard(plan):
    return Storyboard(scene_plans=[ScenePlan(scene_id=1, shots=[
        ShotBrief(shot_id=1, description="Mira at the edge", characters_in_shot=["Mira"], duration_seconds=2),
        ShotBrief(shot_id=2, description="Mira looks on", characters_in_shot=["Mira"], duration_seconds=2),
    ])], source_plan_id=plan.plan_id)


def _make_shot_plan(storyboard):
    return ShotPlan(scene_plans=[ShotScenePlan(scene_id=1, shots=[
        ShotItem(shot_id=1, description="Mira at the edge", characters_in_shot=["Mira"], duration_seconds=2),
        ShotItem(shot_id=2, description="Mira looks on", characters_in_shot=["Mira"], duration_seconds=2),
    ])], source_storyboard_id=storyboard.storyboard_id)


def _make_camera_plan(shot_plan):
    return CameraPlan(scene_plans=[CameraScenePlan(scene_id=1, shots=[
        CameraShot(shot_id=1, camera_angle="wide", camera_movement="static"),
        CameraShot(shot_id=2, camera_angle="close", camera_movement="static"),
    ])], source_shot_plan_id=shot_plan.shot_plan_id)


def _make_character_sheet(plan):
    return CharacterSheet(character_profiles=[CharacterVisualProfile(
        name="Mira", age_range="20s", build="lean", face_details="warm eyes", hair="black",
        outfit="green tunic", color_palette=["green", "brown"], distinguishing_features="a scar",
        art_style_keywords=["3D animated"], reference_prompt="A lean young woman with black hair and warm eyes.",
    )], source_plan_id=plan.plan_id)


def _make_environment_sheet(plan):
    return EnvironmentSheet(environment_profiles=[EnvironmentProfile(
        setting="Forest clearing", time_of_day="dawn", weather="misty", key_visual_elements=["trees"],
        color_palette=["green", "grey"], lighting="soft light", atmosphere="peaceful",
        art_style_keywords=["3D animated"], reference_prompt="A misty forest clearing at dawn with tall trees.",
    )], source_plan_id=plan.plan_id)


def _make_prompt_set(storyboard):
    return PromptSet(source_storyboard_id=storyboard.storyboard_id, shots=[
        ShotPrompt(scene_id=1, shot_id=1, duration_seconds=2,
                   image_prompt="Mira stands at the misty forest edge in a wide cinematic shot at dawn.",
                   video_motion_prompt="Camera holds static as mist drifts."),
        ShotPrompt(scene_id=1, shot_id=2, duration_seconds=2,
                   image_prompt="Close-up of Mira's determined face with warm morning lighting throughout.",
                   video_motion_prompt="Slow push in on Mira's face."),
    ])


def _make_voice_script(plan):
    return VoiceScript(source_plan_id=plan.plan_id,
                       lines=[NarrationLine(scene_id=1, narration_text="Mira stands at the edge.")])


def _edit_plan_ready_project(tmp_path, monkeypatch):
    """Drives the real Director + Producer flow to EDIT_PLAN_READY with media on
    disk, so the Execution Engine has a genuine Producer Package to consume."""
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

    media_dir = manager.get_media_dir(project)
    (media_dir / "images").mkdir(parents=True, exist_ok=True)
    (media_dir / "audio").mkdir(parents=True, exist_ok=True)
    (media_dir / "images" / "scene_1_shot_1.png").write_bytes(b"0" * 6000)
    (media_dir / "images" / "scene_1_shot_2.png").write_bytes(b"1" * 6000)
    (media_dir / "audio" / "voice_script.wav").write_bytes(b"2" * 6000)

    ProducerStudioController(manager).run(project_id=project.project_id)
    project = manager.load_project(project.project_id)
    assert project.status == ProjectState.EDIT_PLAN_READY
    return manager, project


def _package_hashes(package_dir):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package_dir.iterdir()) if p.is_file()
    }


def test_dry_run_builds_command_without_executing_or_touching_state(tmp_path, monkeypatch):
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    before = _package_hashes(package_dir)

    controller = ExecutionEngineController(manager, detector=_available_detector)
    returned_project, info, spec, render_result, validation_report = controller.run(
        project_id=project.project_id, options=RenderOptions(dry_run=True)
    )

    # command built correctly: 2 visual segments + narration audio
    assert info.available is True
    assert len(spec.inputs) == 3
    assert [i.kind for i in spec.inputs] == ["image", "image", "audio"]

    # the real editing plan's single scene / two cut-joined shots compiles to a
    # normalize+concat graph, with the whole edit's own fade-from/to-black
    # (this fixture's only scene is both the first and the last)
    assert spec.filter_complex is not None
    assert "concat=n=2:v=1:a=0" in spec.filter_complex
    assert "fade=t=in" in spec.filter_complex
    assert "fade=t=out" in spec.filter_complex
    assert spec.output_args[0] == "-map"
    assert spec.output_args[1].startswith("[") and spec.output_args[1].endswith("]")
    assert spec.output_args[2] == "-map"
    assert spec.output_args[3] == "2:a"  # narration is input index 2 (2 image segments + audio)
    assert spec.output_path.endswith("video.mp4")

    # --dry-run: build + validate + print, but never execute
    assert render_result.dry_run is True
    assert render_result.success is True
    assert render_result.exit_code is None
    assert render_result.output_path is None
    assert validation_report is None  # nothing was produced to probe

    # state unchanged, no renders/ dir, package untouched
    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.EDIT_PLAN_READY
    assert not (tmp_path / "projects" / project.project_id / "renders").exists()
    assert _package_hashes(package_dir) == before


def test_successful_render_and_passing_validation_advances_to_video_rendered(tmp_path, monkeypatch):
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    before = _package_hashes(package_dir)

    controller = ExecutionEngineController(
        manager, detector=_available_detector, executor=_fake_successful_executor, prober=_passing_prober
    )
    project, _info, _spec, render_result, validation_report = controller.run(project_id=project.project_id)

    assert render_result.success is True
    assert validation_report.is_valid is True
    assert [c.passed for c in validation_report.checks] == [True] * len(validation_report.checks)

    # this IS the milestone: process success AND passing validation together
    # advance status, and only together
    assert project.status == ProjectState.VIDEO_RENDERED
    assert project.rendered_video_path == render_result.output_path

    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.VIDEO_RENDERED
    assert _package_hashes(package_dir) == before  # Producer Package still untouched

    render_dir = tmp_path / "projects" / project.project_id / "renders"
    report_written = json.loads((render_dir / "render_report.json").read_text())
    validation_written = json.loads((render_dir / "render_validation.json").read_text())
    assert report_written["success"] is True
    assert validation_written["is_valid"] is True


def test_successful_render_with_failed_validation_does_not_advance_state(tmp_path, monkeypatch):
    """The core verification-gated guarantee: even a real, successful render
    (exit 0, non-empty output) must NOT move the project to VIDEO_RENDERED
    when the rendered file doesn't actually match the expected profile."""
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    package_dir = tmp_path / "projects" / project.project_id / "producer-package"
    before = _package_hashes(package_dir)

    controller = ExecutionEngineController(
        manager, detector=_available_detector, executor=_fake_successful_executor, prober=_wrong_duration_prober
    )
    project, _info, _spec, render_result, validation_report = controller.run(project_id=project.project_id)

    assert render_result.success is True  # ffmpeg "succeeded"...
    assert validation_report.is_valid is False  # ...but the output doesn't match the plan
    failed_checks = [c.name for c in validation_report.checks if not c.passed]
    assert "duration" in failed_checks

    assert project.status == ProjectState.EDIT_PLAN_READY  # NOT VIDEO_RENDERED
    assert project.rendered_video_path is None

    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.EDIT_PLAN_READY
    assert _package_hashes(package_dir) == before

    render_dir = tmp_path / "projects" / project.project_id / "renders"
    assert (render_dir / "render_report.json").exists()
    assert (render_dir / "render_validation.json").exists()  # written even though it failed


def test_unprobeable_output_fails_validation(tmp_path, monkeypatch):
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)

    controller = ExecutionEngineController(
        manager, detector=_available_detector, executor=_fake_successful_executor, prober=_unprobeable_prober
    )
    project, _info, _spec, render_result, validation_report = controller.run(project_id=project.project_id)

    assert render_result.success is True
    assert validation_report.is_valid is False
    assert validation_report.checks[0].name == "probe"
    assert project.status == ProjectState.EDIT_PLAN_READY


def test_failed_render_writes_only_execution_report_no_validation(tmp_path, monkeypatch):
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)

    controller = ExecutionEngineController(
        manager, detector=_available_detector, executor=_fake_failing_executor, prober=_passing_prober
    )
    project, _info, _spec, render_result, validation_report = controller.run(project_id=project.project_id)

    assert render_result.success is False
    assert validation_report is None  # nothing was produced, so nothing to probe/validate

    reloaded = manager.load_project(project.project_id)
    assert reloaded.status == ProjectState.EDIT_PLAN_READY

    render_dir = tmp_path / "projects" / project.project_id / "renders"
    assert (render_dir / "render_report.json").exists()
    assert not (render_dir / "render_validation.json").exists()  # separation: no quality report for a failed run
    report_written = json.loads((render_dir / "render_report.json").read_text())
    assert report_written["success"] is False
    assert report_written["error_type"] == "ffmpeg_failed"


def test_engine_fails_when_ffmpeg_absent(tmp_path, monkeypatch):
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    controller = ExecutionEngineController(manager, detector=_unavailable_detector)

    with pytest.raises(ExecutionEnvironmentError):
        controller.run(project_id=project.project_id)


def test_engine_fails_when_media_missing(tmp_path, monkeypatch):
    manager, project = _edit_plan_ready_project(tmp_path, monkeypatch)
    # delete a required asset after planning completed
    (manager.get_media_dir(project) / "images" / "scene_1_shot_2.png").unlink()

    controller = ExecutionEngineController(manager, detector=_available_detector)
    with pytest.raises(MediaAccessError) as exc:
        controller.run(project_id=project.project_id)
    assert "scene_1_shot_2.png" in str(exc.value)


def test_engine_rejects_project_not_edit_plan_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project()  # status CREATED

    controller = ExecutionEngineController(manager, detector=_available_detector)
    with pytest.raises(RenderInputError, match="not EDIT_PLAN_READY"):
        controller.run(project_id=project.project_id)

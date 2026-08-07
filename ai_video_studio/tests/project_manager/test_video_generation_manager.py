import json
from pathlib import Path

from config import settings
from project_manager.manager import ProjectManager
from project_manager.project import ProjectState
from shared_core.contracts.video_generation import (
    ShotMediaSelection,
    VideoAsset,
    VideoGenerationResult,
    VideoGenerationValidationReport,
)


def _project_with_package(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    pm = ProjectManager()
    project = pm.create_project()
    package_dir = tmp_path / "projects" / project.project_id / "production-package"
    package_dir.mkdir(parents=True)
    project = project.model_copy(update={
        "status": ProjectState.PACKAGE_READY,
        "production_package_dir": str(package_dir),
        "source_prompt_set_id": "ps-1",
    })
    return pm, project


def test_get_media_video_dir_matches_naming_convention(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)
    expected = tmp_path / "projects" / project.project_id / "media" / "video"
    assert pm.get_media_video_dir(project) == expected


def test_load_video_generation_manifest_is_none_when_never_written(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)
    assert pm.load_video_generation_manifest(project) is None


def test_save_video_generation_result_writes_manifest_and_updates_project(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)

    selections = [ShotMediaSelection(scene_id=1, shot_id=1, mode="video")]
    assets = [VideoAsset(scene_id=1, shot_id=1, file_path="x.mp4", prompt_used="p", provider="stub")]
    results = [VideoGenerationResult(success=True, provider="stub", scene_id=1, shot_id=1)]
    reports = [VideoGenerationValidationReport(is_valid=True, output_path="x.mp4")]

    updated = pm.save_video_generation_result(
        project, selections=selections, new_assets=assets, results=results, validation_reports=reports,
    )

    assert updated.video_generation_status == "complete"
    assert updated.video_generation_manifest_path is not None
    manifest_path = Path(updated.video_generation_manifest_path)
    assert manifest_path.is_file()
    assert manifest_path.name == "video_manifest.json"
    data = json.loads(manifest_path.read_text())
    assert data["assets"][0]["scene_id"] == 1
    assert data["selections"][0]["mode"] == "video"


def test_save_video_generation_result_never_advances_project_status(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)
    selections = [ShotMediaSelection(scene_id=1, shot_id=1, mode="video")]
    assets = [VideoAsset(scene_id=1, shot_id=1, file_path="x.mp4", prompt_used="p", provider="stub")]

    updated = pm.save_video_generation_result(
        project, selections=selections, new_assets=assets, results=[], validation_reports=[],
    )

    # Asset Validation, unchanged, remains the sole gate to MEDIA_IMPORTED.
    assert updated.status == project.status == ProjectState.PACKAGE_READY


def test_save_video_generation_result_merges_across_two_separate_runs(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)

    project = pm.save_video_generation_result(
        project,
        selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        new_assets=[VideoAsset(scene_id=1, shot_id=1, file_path="a.mp4", prompt_used="p", provider="stub")],
        results=[], validation_reports=[],
    )
    project = pm.save_video_generation_result(
        project,
        selections=[ShotMediaSelection(scene_id=1, shot_id=2, mode="video")],
        new_assets=[VideoAsset(scene_id=1, shot_id=2, file_path="b.mp4", prompt_used="p", provider="stub")],
        results=[], validation_reports=[],
    )

    manifest = pm.load_video_generation_manifest(project)
    assert {(a.scene_id, a.shot_id) for a in manifest.assets} == {(1, 1), (1, 2)}
    assert {(s.scene_id, s.shot_id) for s in manifest.selections} == {(1, 1), (1, 2)}


def test_save_video_generation_result_reports_partial_status_when_shots_missing(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)
    selections = [
        ShotMediaSelection(scene_id=1, shot_id=1, mode="video"),
        ShotMediaSelection(scene_id=1, shot_id=2, mode="video"),
    ]
    assets = [VideoAsset(scene_id=1, shot_id=1, file_path="a.mp4", prompt_used="p", provider="stub")]

    updated = pm.save_video_generation_result(
        project, selections=selections, new_assets=assets, results=[], validation_reports=[],
    )

    assert updated.video_generation_status == "partial"


def test_save_video_generation_result_reports_not_started_for_image_only_selections(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)
    selections = [ShotMediaSelection(scene_id=1, shot_id=1, mode="image")]

    updated = pm.save_video_generation_result(
        project, selections=selections, new_assets=[], results=[], validation_reports=[],
    )

    assert updated.video_generation_status == "not_started"


def test_save_video_generation_result_does_not_modify_existing_image_outputs(tmp_path, monkeypatch):
    pm, project = _project_with_package(tmp_path, monkeypatch)
    # A legacy flat-file image output already on disk, untouched by anything
    # video-generation-related (requirement 6: "do not modify existing
    # image outputs").
    legacy_image_manifest = tmp_path / "image_manifest.json"
    legacy_image_manifest.write_text(json.dumps({"untouched": True}))

    pm.save_video_generation_result(
        project, selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        new_assets=[], results=[], validation_reports=[],
    )

    assert json.loads(legacy_image_manifest.read_text()) == {"untouched": True}

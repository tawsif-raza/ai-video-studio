from shared_core.contracts.prompt_set import ShotPrompt
from shared_core.contracts.video_generation import (
    ProviderInfo,
    ShotMediaSelection,
    VideoAsset,
    VideoGenerationManifest,
    VideoGenerationOptions,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationStatus,
    VideoGenerationValidationReport,
)


def _shot_prompt(**overrides):
    defaults = dict(
        scene_id=1, shot_id=1, duration_seconds=5,
        image_prompt="x" * 50, video_motion_prompt="camera pans slowly across the scene",
    )
    defaults.update(overrides)
    return ShotPrompt(**defaults)


def test_video_generation_options_defaults():
    options = VideoGenerationOptions()
    assert options.provider == "google_veo"  # not the stub - see module docstring
    assert options.aspect_ratio == "9:16"
    assert options.resolution is None
    assert options.fps == 30
    assert options.seed_image_path is None
    assert options.dry_run is False
    assert options.poll_interval_seconds == 10
    assert options.max_poll_attempts == 60


def test_shot_media_selection_defaults_to_image_mode():
    selection = ShotMediaSelection(scene_id=1, shot_id=1)
    assert selection.mode == "image"


def test_video_generation_request_reuses_shot_prompt():
    shot_prompt = _shot_prompt()
    request = VideoGenerationRequest(shot_prompt=shot_prompt, scene_id=1, shot_id=1, output_dir="/media/video")
    assert request.shot_prompt.video_motion_prompt == shot_prompt.video_motion_prompt
    assert isinstance(request.options, VideoGenerationOptions)


def test_video_asset_generates_id_and_timestamp():
    asset = VideoAsset(scene_id=1, shot_id=1, file_path="/x.mp4", prompt_used="p", provider="stub")
    assert asset.asset_id
    assert asset.generated_at is not None


def test_video_generation_result_defaults():
    result = VideoGenerationResult(scene_id=1, shot_id=1, success=True)
    assert result.dry_run is False
    assert result.retry_count == 0
    assert result.error is None
    assert result.error_type is None


def test_video_generation_validation_report_defaults():
    report = VideoGenerationValidationReport(is_valid=True, output_path="/x.mp4")
    assert report.checks == []
    assert report.probed is None


def test_video_generation_manifest_defaults():
    manifest = VideoGenerationManifest()
    assert manifest.manifest_id
    assert manifest.selections == []
    assert manifest.assets == []
    assert manifest.results == []
    assert manifest.validation_reports == []


def test_provider_info_never_carries_a_credential_field():
    # Structural guard, not just documentation: ProviderInfo's declared
    # fields must never grow a raw token/secret field by accident.
    assert set(ProviderInfo.model_fields) == {"provider", "available", "account_label", "detail"}


def test_video_generation_status_shape():
    status = VideoGenerationStatus(status="succeeded", external_job_id="job-1")
    assert status.progress_pct is None

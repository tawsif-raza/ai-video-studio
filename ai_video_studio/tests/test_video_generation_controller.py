import pytest

from project_manager.project import Project, ProjectState
from shared_core.contracts.prompt_set import PromptSet, ShotPrompt
from shared_core.contracts.render import ProbedMedia
from shared_core.contracts.video_generation import (
    ProviderInfo,
    ShotMediaSelection,
    VideoAsset,
    VideoGenerationManifest,
    VideoGenerationOptions,
    VideoGenerationResult,
)
from video_generation_engine.controller import VideoGenerationEngineController
from video_generation_engine.errors import VideoGenerationEnvironmentError, VideoGenerationInputError
from video_generation_engine.providers.base import VideoGenerationProvider


def _shot_prompt(scene_id, shot_id, **overrides):
    defaults = dict(
        scene_id=scene_id, shot_id=shot_id, duration_seconds=5,
        image_prompt="x" * 50, video_motion_prompt="camera pans across the scene slowly",
    )
    defaults.update(overrides)
    return ShotPrompt(**defaults)


def _prompt_set():
    return PromptSet(shots=[_shot_prompt(1, 1), _shot_prompt(1, 2)])


def _project(status=ProjectState.PACKAGE_READY):
    return Project(status=status, source_prompt_set_id="ps-1", production_package_dir="/pkg")


def _fixed_prober(**overrides):
    defaults = dict(
        duration_seconds=5.0, has_video_stream=True, video_width=720, video_height=1280,
        video_fps=30.0, video_codec="h264",
    )
    defaults.update(overrides)

    def _prober(path):
        return ProbedMedia(**defaults)

    return _prober


class _FakeProvider(VideoGenerationProvider):
    provider_name = "fake"

    def __init__(self, *, available=True, generate_success=True):
        self.available = available
        self.generate_success = generate_success
        self.generate_calls = []

    def authenticate(self):
        return ProviderInfo(
            provider="fake", available=self.available, account_label="fake-account",
            detail=None if self.available else "provider unavailable",
        )

    def generate(self, request):
        self.generate_calls.append(request)
        if not self.generate_success:
            return VideoGenerationResult(
                success=False, provider="fake", scene_id=request.scene_id, shot_id=request.shot_id,
                error="boom", error_type="generation_failed",
            )
        return VideoGenerationResult(
            success=True, provider="fake", scene_id=request.scene_id, shot_id=request.shot_id,
            external_job_id="job-1",
        )

    def check_status(self, external_job_id):
        raise AssertionError("check_status must never be called by the controller in Milestone V2")


class _FakeProjectManager:
    def __init__(self, *, project, prompt_set, media_video_dir, existing_manifest=None):
        self.project = project
        self.prompt_set = prompt_set
        self.media_video_dir = media_video_dir
        self.existing_manifest = existing_manifest
        self.save_calls = []

    def load_project(self, project_id):
        return self.project

    def load_prompt_set(self, project):
        return self.prompt_set

    def load_video_generation_manifest(self, project):
        return self.existing_manifest

    def get_media_video_dir(self, project):
        return self.media_video_dir

    def save_video_generation_result(self, project, *, selections, new_assets, results, validation_reports):
        self.save_calls.append(dict(
            selections=selections, new_assets=new_assets, results=results, validation_reports=validation_reports,
        ))
        video_selected = sum(1 for s in selections if s.mode == "video")
        status = "complete" if new_assets and len(new_assets) == video_selected else "partial"
        return project.model_copy(update={"video_generation_status": status})


def _controller(pm, *, provider=None, available=True, generate_success=True, prober=None):
    provider = provider or _FakeProvider(available=available, generate_success=generate_success)
    return VideoGenerationEngineController(
        pm, provider_resolver=lambda name: (lambda: provider), prober=prober or _fixed_prober(),
    ), provider


# ---- project-state gate ----

def test_run_rejects_project_at_wrong_status(tmp_path):
    pm = _FakeProjectManager(project=_project(status=ProjectState.CREATED), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, _ = _controller(pm)

    with pytest.raises(VideoGenerationInputError):
        controller.run(project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")])


# ---- dry-run ----

def test_dry_run_never_calls_provider_generate_or_persists(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, provider = _controller(pm)

    project, info, results, reports = controller.run(
        project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        options=VideoGenerationOptions(provider="fake", dry_run=True),
    )

    assert all(r.dry_run for r in results)
    assert provider.generate_calls == []
    assert pm.save_calls == []
    assert reports == []


# ---- happy path ----

def test_happy_path_generates_validates_and_persists(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, provider = _controller(pm)

    project, info, results, reports = controller.run(
        project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        options=VideoGenerationOptions(provider="fake"),
    )

    assert len(results) == 1 and results[0].success is True
    assert len(reports) == 1 and reports[0].is_valid is True
    assert len(pm.save_calls) == 1
    assert len(pm.save_calls[0]["new_assets"]) == 1
    assert provider.generate_calls[0].scene_id == 1
    assert provider.generate_calls[0].shot_id == 1
    assert project.video_generation_status == "complete"


def test_image_mode_selections_are_never_generated(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, provider = _controller(pm)

    controller.run(
        project_id="p1",
        selections=[
            ShotMediaSelection(scene_id=1, shot_id=1, mode="image"),
            ShotMediaSelection(scene_id=1, shot_id=2, mode="video"),
        ],
        options=VideoGenerationOptions(provider="fake"),
    )

    assert len(provider.generate_calls) == 1
    assert provider.generate_calls[0].shot_id == 2


# ---- idempotency: skip already-generated shots ----

def test_already_generated_shots_are_skipped_by_default(tmp_path):
    existing = VideoGenerationManifest(
        assets=[VideoAsset(scene_id=1, shot_id=1, file_path="x", prompt_used="p", provider="fake")]
    )
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path, existing_manifest=existing)
    controller, provider = _controller(pm)

    project, info, results, reports = controller.run(
        project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        options=VideoGenerationOptions(provider="fake"),
    )

    assert provider.generate_calls == []
    assert results == []
    assert pm.save_calls == []


# ---- provider resolution / environment ----

def test_default_options_provider_is_unregistered_google_veo(tmp_path):
    # Hard verification of this milestone's constraint using the REAL
    # registry (no fake resolver): a caller who never specifies
    # options.provider must not reach any registered adapter.
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller = VideoGenerationEngineController(pm)

    with pytest.raises(VideoGenerationInputError) as exc:
        controller.run(project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")])
    assert "google_veo" in str(exc.value)


def test_unregistered_provider_name_raises_input_error(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)

    def _resolver(name):
        from video_generation_engine.errors import VideoGenerationInputError as E
        raise E(f"Unknown video generation provider '{name}'.")

    controller = VideoGenerationEngineController(pm, provider_resolver=_resolver, prober=_fixed_prober())

    with pytest.raises(VideoGenerationInputError):
        controller.run(project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")])


def test_unavailable_provider_raises_environment_error(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, _ = _controller(pm, available=False)

    with pytest.raises(VideoGenerationEnvironmentError):
        controller.run(
            project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
            options=VideoGenerationOptions(provider="fake"),
        )


# ---- input validation ----

def test_unknown_shot_selection_raises_input_error(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, _ = _controller(pm)

    with pytest.raises(VideoGenerationInputError):
        controller.run(project_id="p1", selections=[ShotMediaSelection(scene_id=99, shot_id=99, mode="video")])


# ---- failure handling ----

def test_generation_failure_is_reported_and_not_persisted_as_an_asset(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    controller, provider = _controller(pm, generate_success=False)

    project, info, results, reports = controller.run(
        project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        options=VideoGenerationOptions(provider="fake"),
    )

    assert results[0].success is False
    assert reports == []  # nothing to probe/validate for a failed generation
    assert pm.save_calls[0]["new_assets"] == []


def test_postflight_failure_is_reported_and_not_persisted_as_an_asset(tmp_path):
    pm = _FakeProjectManager(project=_project(), prompt_set=_prompt_set(), media_video_dir=tmp_path)
    # Prober returns a duration wildly outside tolerance, failing postflight
    # even though generation itself "succeeded".
    controller, provider = _controller(pm, prober=_fixed_prober(duration_seconds=999.0))

    project, info, results, reports = controller.run(
        project_id="p1", selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
        options=VideoGenerationOptions(provider="fake"),
    )

    assert results[0].success is True
    assert reports[0].is_valid is False
    assert pm.save_calls[0]["new_assets"] == []

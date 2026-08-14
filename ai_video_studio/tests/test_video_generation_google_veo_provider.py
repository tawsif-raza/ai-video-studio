"""
Unit/integration tests for GoogleVeoProvider (Milestone V3: Real Google Veo
Provider). Every test injects a fake `client` (standing in for the
google-genai SDK's Client) and, where relevant, a fake `downloader` callable
- GoogleVeoProvider never constructs a real google.genai.Client or performs
a real HTTP request in any test here, so this suite makes zero real network
calls, the same guarantee test_video_generation_stub_provider.py establishes
for the local stub (there via "no network library is even imported"; here
via "the network boundary is always injected and fake").
"""

import pytest

from project_manager.project import Project, ProjectState
from shared_core.contracts.prompt_set import PromptSet, ShotPrompt
from shared_core.contracts.video_generation import (
    ShotMediaSelection,
    VideoGenerationOptions,
    VideoGenerationRequest,
)
from video_generation_engine.controller import VideoGenerationEngineController
from video_generation_engine.providers.google_veo import GoogleVeoProvider


def _shot_prompt(**overrides):
    defaults = dict(
        scene_id=1, shot_id=1, duration_seconds=8,
        image_prompt="x" * 50, video_motion_prompt="camera pans slowly across the scene",
    )
    defaults.update(overrides)
    return ShotPrompt(**defaults)


def _request(*, shot_prompt=None, output_dir=".", **option_overrides):
    defaults = dict(provider="google_veo", aspect_ratio="9:16", poll_interval_seconds=0)
    defaults.update(option_overrides)
    options = VideoGenerationOptions(**defaults)
    shot_prompt = shot_prompt or _shot_prompt()
    return VideoGenerationRequest(
        shot_prompt=shot_prompt, scene_id=shot_prompt.scene_id, shot_id=shot_prompt.shot_id,
        output_dir=output_dir, options=options,
    )


# ---- fakes standing in for the google-genai SDK's own shapes ----

class _FakeVideo:
    def __init__(self, *, uri=None, video_bytes=None):
        self.uri = uri
        self.video_bytes = video_bytes


class _FakeGeneratedVideo:
    def __init__(self, video):
        self.video = video


class _FakeResponse:
    def __init__(self, *, generated_videos=None, rai_media_filtered_reasons=None):
        self.generated_videos = generated_videos or []
        self.rai_media_filtered_reasons = rai_media_filtered_reasons


class _FakeOperation:
    def __init__(self, *, name="op-1", done=False, error=None, response=None):
        self.name = name
        self.done = done
        self.error = error
        self.response = response
        self.result = response


class _RaisingAPIError(Exception):
    """Stands in for google.genai.errors.APIError, which carries an HTTP
    status code on `.code` - GoogleVeoProvider._classify_exception reads
    exactly that attribute."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class _FakeModels:
    def __init__(self, *, operation=None, raises=None, record=None):
        self._operation = operation
        self._raises = raises
        self.record = record if record is not None else []

    def generate_videos(self, **kwargs):
        self.record.append(kwargs)
        if self._raises:
            raise self._raises
        return self._operation


class _FakeOperations:
    def __init__(self, *, sequence=None, raises=None):
        self._sequence = list(sequence or [])
        self._raises = raises
        self.calls = 0

    def get(self, operation):
        self.calls += 1
        if self._raises:
            raise self._raises
        if self._sequence:
            return self._sequence.pop(0)
        return operation  # echoes back whatever was last submitted (still not done)


class _FakeClient:
    def __init__(self, *, models=None, operations=None):
        self.models = models or _FakeModels()
        self.operations = operations or _FakeOperations()


def _no_sleep(monkeypatch):
    monkeypatch.setattr("video_generation_engine.providers.google_veo.time.sleep", lambda _seconds: None)


# ---- credentials (requirement: missing credentials) ----

def test_authenticate_reports_unavailable_without_credentials():
    info = GoogleVeoProvider(api_key="").authenticate()
    assert info.available is False
    assert "credentials" in info.detail.lower()


def test_authenticate_reports_available_with_credentials():
    info = GoogleVeoProvider(api_key="fake-key").authenticate()
    assert info.available is True
    assert info.provider == "google_veo"
    assert info.account_label is not None


def test_generate_fails_closed_without_credentials_and_never_touches_client():
    class _ExplodingClient:
        @property
        def models(self):
            raise AssertionError("must never construct/use a client with no credentials")

    provider = GoogleVeoProvider(api_key="", client=_ExplodingClient())

    result = provider.generate(_request())

    assert result.success is False
    assert result.error_type == "auth_failed"


# ---- malformed request: rejected before any client/network use ----

def test_generate_rejects_unsupported_aspect_ratio_before_calling_client(tmp_path):
    class _ExplodingClient:
        @property
        def models(self):
            raise AssertionError("must not use the client for a malformed request")

    provider = GoogleVeoProvider(api_key="fake-key", client=_ExplodingClient())

    result = provider.generate(_request(output_dir=str(tmp_path), aspect_ratio="4:3"))

    assert result.success is False
    assert result.error_type == "generation_failed"
    assert "aspect_ratio" in result.error


def test_generate_rejects_unsupported_resolution_before_calling_client(tmp_path):
    class _ExplodingClient:
        @property
        def models(self):
            raise AssertionError("must not use the client for a malformed request")

    provider = GoogleVeoProvider(api_key="fake-key", client=_ExplodingClient())

    result = provider.generate(_request(output_dir=str(tmp_path), resolution="4k"))

    assert result.success is False
    assert "resolution" in result.error


def test_generate_rejects_missing_seed_image_before_calling_client(tmp_path):
    class _ExplodingClient:
        @property
        def models(self):
            raise AssertionError("must not use the client when the seed image is missing")

    provider = GoogleVeoProvider(api_key="fake-key", client=_ExplodingClient())
    request = _request(output_dir=str(tmp_path), seed_image_path=str(tmp_path / "missing.png"))

    result = provider.generate(request)

    assert result.success is False
    assert "seed image" in result.error


# ---- submission failure ----

def test_generate_reports_submission_failure(tmp_path):
    client = _FakeClient(models=_FakeModels(raises=_RaisingAPIError("bad request", 400)))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is False
    assert result.error_type == "generation_failed"
    assert result.error


def test_generate_classifies_auth_error_from_submission(tmp_path):
    client = _FakeClient(models=_FakeModels(raises=_RaisingAPIError("unauthorized", 401)))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.error_type == "auth_failed"


def test_generate_classifies_quota_error_from_submission(tmp_path):
    client = _FakeClient(models=_FakeModels(raises=_RaisingAPIError("rate limited", 429)))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.error_type == "quota_exceeded"


# ---- request mapping (verified through the actual call sent, not internals) ----

def test_generate_maps_options_into_veo_config(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    video = _FakeVideo(video_bytes=b"x")
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    record = []
    client = _FakeClient(models=_FakeModels(operation=final_op, record=record))
    provider = GoogleVeoProvider(api_key="fake-key", model="veo-3.1-fast-generate-preview", client=client)

    shot_prompt = _shot_prompt(duration_seconds=5)
    request = _request(shot_prompt=shot_prompt, output_dir=str(tmp_path), aspect_ratio="9:16", resolution="1920x1080")

    result = provider.generate(request)

    assert result.success is True
    assert len(record) == 1
    assert record[0]["model"] == "veo-3.1-fast-generate-preview"
    assert record[0]["prompt"]
    sent_config = record[0]["config"]
    assert sent_config.aspect_ratio == "9:16"
    assert sent_config.resolution == "1080p"  # mapped from the "1920x1080" alias
    assert sent_config.duration_seconds in (4, 6)  # nearest supported value to 5s
    assert sent_config.number_of_videos == 1


def test_generate_passes_seed_image_when_provided(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    seed = tmp_path / "seed.png"
    seed.write_bytes(b"\x89PNG\r\n\x1a\n")
    video = _FakeVideo(video_bytes=b"x")
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    record = []
    client = _FakeClient(models=_FakeModels(operation=final_op, record=record))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path), seed_image_path=str(seed)))

    assert result.success is True
    assert record[0]["image"] is not None


# ---- polling ----

def test_generate_polls_until_done(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    video = _FakeVideo(video_bytes=b"fake-mp4-bytes")
    final_op = _FakeOperation(name="op-1", done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    pending = [_FakeOperation(name="op-1", done=False), _FakeOperation(name="op-1", done=False), final_op]
    client = _FakeClient(
        models=_FakeModels(operation=_FakeOperation(name="op-1", done=False)),
        operations=_FakeOperations(sequence=pending),
    )
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path), max_poll_attempts=10))

    assert result.success is True
    assert client.operations.calls == 3
    assert (tmp_path / "scene_1_shot_1.mp4").read_bytes() == b"fake-mp4-bytes"


def test_generate_never_busy_loops_sleeps_between_every_poll(tmp_path, monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("video_generation_engine.providers.google_veo.time.sleep", lambda s: sleep_calls.append(s))
    video = _FakeVideo(video_bytes=b"x")
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    client = _FakeClient(
        models=_FakeModels(operation=_FakeOperation(done=False)),
        operations=_FakeOperations(sequence=[_FakeOperation(done=False), final_op]),
    )
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    provider.generate(_request(output_dir=str(tmp_path), poll_interval_seconds=7, max_poll_attempts=10))

    assert sleep_calls == [7, 7]


# ---- timeout ----

def test_generate_times_out_after_max_poll_attempts(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    client = _FakeClient(
        models=_FakeModels(operation=_FakeOperation(done=False)),
        operations=_FakeOperations(),  # always echoes back a not-done operation
    )
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path), max_poll_attempts=3))

    assert result.success is False
    assert result.error_type == "timeout"
    assert client.operations.calls == 3
    assert not (tmp_path / "scene_1_shot_1.mp4").exists()


def test_generate_times_out_on_wall_clock_deadline(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    clock = iter([0.0, 100.0])
    monkeypatch.setattr("video_generation_engine.providers.google_veo.time.monotonic", lambda: next(clock))
    client = _FakeClient(
        models=_FakeModels(operation=_FakeOperation(done=False)),
        operations=_FakeOperations(),
    )
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path), max_poll_attempts=1000, timeout_seconds=5))

    assert result.success is False
    assert result.error_type == "timeout"


# ---- generation failure (terminal, but unsuccessful) ----

def test_generate_reports_content_filtered_when_rai_filtered(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    final_op = _FakeOperation(
        done=True, response=_FakeResponse(generated_videos=[], rai_media_filtered_reasons=["adult content"]),
    )
    client = _FakeClient(models=_FakeModels(operation=final_op))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is False
    assert result.error_type == "content_filtered"
    assert "adult content" in result.error


def test_generate_reports_operation_error(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    final_op = _FakeOperation(done=True, error={"code": 500, "message": "internal error"})
    client = _FakeClient(models=_FakeModels(operation=final_op))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is False
    assert result.error_type == "generation_failed"
    assert "internal error" in result.error


def test_generate_reports_failure_when_no_video_returned(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[]))
    client = _FakeClient(models=_FakeModels(operation=final_op))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is False
    assert result.error_type == "generation_failed"


# ---- download ----

def test_generate_uses_injected_downloader_for_uri_only_video(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    video = _FakeVideo(uri="https://example.invalid/download/abc")
    final_op = _FakeOperation(name="op-42", done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    client = _FakeClient(models=_FakeModels(operation=final_op))

    calls = []

    def _downloader(uri, output_path):
        calls.append((uri, output_path))
        output_path.write_bytes(b"downloaded-bytes")
        return len(b"downloaded-bytes")

    provider = GoogleVeoProvider(api_key="fake-key", client=client, downloader=_downloader)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is True
    assert result.external_job_id == "op-42"
    assert calls == [("https://example.invalid/download/abc", tmp_path / "scene_1_shot_1.mp4")]
    assert (tmp_path / "scene_1_shot_1.mp4").read_bytes() == b"downloaded-bytes"


def test_generate_reports_download_failure(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    video = _FakeVideo(uri="https://example.invalid/download/abc")
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    client = _FakeClient(models=_FakeModels(operation=final_op))

    def _failing_downloader(uri, output_path):
        raise RuntimeError("connection reset")

    provider = GoogleVeoProvider(api_key="fake-key", client=client, downloader=_failing_downloader)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is False
    assert result.error_type == "generation_failed"
    assert not (tmp_path / "scene_1_shot_1.mp4").exists()


# ---- successful VideoGenerationResult (in-memory video_bytes path) ----

def test_generate_succeeds_and_writes_the_clip_at_the_deterministic_path(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    video = _FakeVideo(video_bytes=b"real-bytes-stand-in")
    final_op = _FakeOperation(name="op-99", done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    client = _FakeClient(models=_FakeModels(operation=final_op))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    result = provider.generate(_request(output_dir=str(tmp_path)))

    assert result.success is True
    assert result.provider == "google_veo"
    assert result.external_job_id == "op-99"
    assert result.error is None
    assert result.started_at is not None and result.finished_at is not None
    output_path = tmp_path / "scene_1_shot_1.mp4"
    assert output_path.is_file()
    assert output_path.read_bytes() == b"real-bytes-stand-in"


# ---- check_status() ----

def test_check_status_reports_succeeded():
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[]))
    client = _FakeClient(operations=_FakeOperations(sequence=[final_op]))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    status = provider.check_status("op-1")

    assert status.status == "succeeded"
    assert status.external_job_id == "op-1"


def test_check_status_reports_generating_when_not_done():
    client = _FakeClient(operations=_FakeOperations(sequence=[_FakeOperation(done=False)]))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    status = provider.check_status("op-1")

    assert status.status == "generating"


def test_check_status_reports_failed_on_operation_error():
    client = _FakeClient(operations=_FakeOperations(sequence=[_FakeOperation(done=True, error={"message": "boom"})]))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    status = provider.check_status("op-1")

    assert status.status == "failed"


# ---- persistence failure (controller-level, through the real controller) ----

def test_controller_persistence_failure_propagates_after_a_successful_generation(tmp_path, monkeypatch):
    _no_sleep(monkeypatch)
    video = _FakeVideo(video_bytes=b"x")
    final_op = _FakeOperation(done=True, response=_FakeResponse(generated_videos=[_FakeGeneratedVideo(video)]))
    client = _FakeClient(models=_FakeModels(operation=final_op))
    provider = GoogleVeoProvider(api_key="fake-key", client=client)

    class _BoomProjectManager:
        def load_project(self, project_id):
            return Project(status=ProjectState.PACKAGE_READY, source_prompt_set_id="ps-1", production_package_dir=str(tmp_path))

        def load_prompt_set(self, project):
            return PromptSet(shots=[_shot_prompt()])

        def load_video_generation_manifest(self, project):
            return None

        def get_media_video_dir(self, project):
            return tmp_path

        def save_video_generation_result(self, project, **kwargs):
            raise RuntimeError("disk full")

    controller = VideoGenerationEngineController(_BoomProjectManager(), provider_resolver=lambda name: (lambda: provider))

    with pytest.raises(RuntimeError, match="disk full"):
        controller.run(
            project_id="p1",
            selections=[ShotMediaSelection(scene_id=1, shot_id=1, mode="video")],
            options=VideoGenerationOptions(provider="google_veo", poll_interval_seconds=0),
        )

    # The clip itself is already on disk by the time persistence fails -
    # a failed save doesn't retroactively delete a real generated asset.
    assert (tmp_path / "scene_1_shot_1.mp4").exists()

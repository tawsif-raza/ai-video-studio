import inspect
import shutil

import pytest

from shared_core.contracts.prompt_set import ShotPrompt
from shared_core.contracts.video_generation import VideoGenerationOptions, VideoGenerationRequest
from video_generation_engine import ffprobe_client
from video_generation_engine.providers import stub as stub_module
from video_generation_engine.providers.stub import StubProvider

_ffmpeg_available = shutil.which("ffmpeg") is not None
pytestmark = pytest.mark.skipif(not _ffmpeg_available, reason="ffmpeg not available on this machine")


def _shot_prompt(**overrides):
    defaults = dict(
        scene_id=1, shot_id=1, duration_seconds=2,
        image_prompt="x" * 50, video_motion_prompt="camera pans slowly across the scene",
    )
    defaults.update(overrides)
    return ShotPrompt(**defaults)


def _request(tmp_path, *, shot_prompt=None, **option_overrides):
    defaults = dict(provider="stub", resolution="640x360", aspect_ratio="16:9", fps=24)
    defaults.update(option_overrides)
    options = VideoGenerationOptions(**defaults)
    shot_prompt = shot_prompt or _shot_prompt()
    return VideoGenerationRequest(
        shot_prompt=shot_prompt, scene_id=shot_prompt.scene_id, shot_id=shot_prompt.shot_id,
        output_dir=str(tmp_path), options=options,
    )


# ---- zero external APIs (requirement 4) ----

def test_stub_module_never_references_network_libraries():
    source = inspect.getsource(stub_module)
    forbidden = ("import requests", "import urllib", "import httpx", "http.client", "import socket", "aiohttp")
    for term in forbidden:
        assert term not in source, f"StubProvider must never reference {term!r} - it is required to be zero-network"


# ---- authenticate() ----

def test_authenticate_reports_available_when_ffmpeg_present():
    info = StubProvider().authenticate()
    assert info.available is True
    assert info.provider == "stub"
    assert info.account_label is not None


def test_authenticate_reports_unavailable_when_ffmpeg_missing():
    info = StubProvider(ffmpeg_path="definitely-not-a-real-ffmpeg-binary").authenticate()
    assert info.available is False
    assert info.detail is not None


# ---- generate(): happy path + configurability (requirement 4) ----

def test_generate_produces_a_clip_at_the_expected_deterministic_path(tmp_path):
    request = _request(tmp_path)

    result = StubProvider().generate(request)

    assert result.success is True
    assert result.provider == "stub"
    assert result.external_job_id
    output_path = tmp_path / "scene_1_shot_1.mp4"
    assert output_path.is_file()
    assert output_path.stat().st_size > 0


def test_generate_output_matches_configured_duration_resolution_and_fps(tmp_path):
    shot_prompt = _shot_prompt(duration_seconds=3)
    request = _request(tmp_path, shot_prompt=shot_prompt, resolution="480x270", fps=15)

    StubProvider().generate(request)

    probed = ffprobe_client.probe(str(tmp_path / "scene_1_shot_1.mp4"))
    assert probed is not None
    assert probed.has_video_stream is True
    assert probed.video_width == 480
    assert probed.video_height == 270
    assert probed.video_fps == 15.0
    assert abs(probed.duration_seconds - 3.0) < 0.5


# ---- determinism (requirement 4) ----

def test_generate_is_byte_for_byte_deterministic_for_identical_requests(tmp_path):
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    provider = StubProvider()

    provider.generate(_request(dir_a))
    provider.generate(_request(dir_b))

    assert (dir_a / "scene_1_shot_1.mp4").read_bytes() == (dir_b / "scene_1_shot_1.mp4").read_bytes()


def test_generate_output_differs_when_shot_identity_differs(tmp_path):
    # Sanity check for the determinism test above: different inputs must not
    # coincidentally produce the same bytes (the overlay text differs).
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    provider = StubProvider()

    provider.generate(_request(dir_a, shot_prompt=_shot_prompt(scene_id=1, shot_id=1)))
    provider.generate(_request(dir_b, shot_prompt=_shot_prompt(scene_id=2, shot_id=9)))

    bytes_a = (dir_a / "scene_1_shot_1.mp4").read_bytes()
    bytes_b = (dir_b / "scene_2_shot_9.mp4").read_bytes()
    assert bytes_a != bytes_b


# ---- failure handling ----

def test_generate_reports_failure_for_invalid_resolution(tmp_path):
    request = _request(tmp_path, resolution="not-a-resolution")

    result = StubProvider().generate(request)

    assert result.success is False
    assert result.error_type == "generation_failed"
    assert result.error
    assert not (tmp_path / "scene_1_shot_1.mp4").exists()


def test_generate_reports_failure_when_ffmpeg_missing(tmp_path):
    request = _request(tmp_path)

    result = StubProvider(ffmpeg_path="definitely-not-a-real-ffmpeg-binary").generate(request)

    assert result.success is False
    assert result.error_type == "generation_failed"


def test_generate_never_raises_it_always_returns_a_result(tmp_path):
    request = _request(tmp_path, resolution="0x0")

    result = StubProvider().generate(request)  # must not raise

    assert result.success is False


# ---- check_status() shape symmetry ----

def test_check_status_reports_immediate_terminal_status():
    status = StubProvider().check_status("some-job-id")
    assert status.status == "succeeded"
    assert status.external_job_id == "some-job-id"

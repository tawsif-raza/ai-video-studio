import json
import subprocess

from execution_engine import ffprobe_client
from execution_engine.ffprobe_client import probe

_PROBE_JSON = json.dumps({
    "format": {"duration": "20.041667"},
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
})


def _completed(returncode=0, stdout=_PROBE_JSON, stderr=""):
    return subprocess.CompletedProcess(args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_probe_parses_duration_and_both_streams(monkeypatch):
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffprobe_client.subprocess, "run", lambda *a, **k: _completed())

    result = probe("/renders/video.mp4")

    assert result.duration_seconds == 20.041667
    assert result.has_video_stream is True
    assert result.video_width == 1920
    assert result.video_height == 1080
    assert result.video_fps == 30.0
    assert result.video_codec == "h264"
    assert result.has_audio_stream is True
    assert result.audio_codec == "aac"


def test_probe_handles_fractional_frame_rate(monkeypatch):
    data = json.dumps({
        "format": {"duration": "10.0"},
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720, "r_frame_rate": "30000/1001"}],
    })
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffprobe_client.subprocess, "run", lambda *a, **k: _completed(stdout=data))

    result = probe("/renders/video.mp4")

    assert abs(result.video_fps - 29.97) < 0.01


def test_probe_video_only_reports_no_audio_stream(monkeypatch):
    data = json.dumps({
        "format": {"duration": "5.0"},
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 640, "height": 480, "r_frame_rate": "25/1"}],
    })
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffprobe_client.subprocess, "run", lambda *a, **k: _completed(stdout=data))

    result = probe("/renders/video.mp4")

    assert result.has_video_stream is True
    assert result.has_audio_stream is False
    assert result.audio_codec is None


def test_probe_returns_none_when_ffprobe_not_on_path(monkeypatch):
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: None)

    assert probe("/renders/video.mp4") is None


def test_probe_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffprobe_client.subprocess, "run", lambda *a, **k: _completed(returncode=1, stdout=""))

    assert probe("/renders/video.mp4") is None


def test_probe_returns_none_on_unparseable_output(monkeypatch):
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffprobe_client.subprocess, "run", lambda *a, **k: _completed(stdout="not json"))

    assert probe("/renders/video.mp4") is None


def test_probe_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

    monkeypatch.setattr(ffprobe_client.subprocess, "run", _timeout)

    assert probe("/renders/video.mp4") is None


def test_probe_returns_none_on_missing_duration_field(monkeypatch):
    data = json.dumps({"format": {}, "streams": []})
    monkeypatch.setattr(ffprobe_client.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(ffprobe_client.subprocess, "run", lambda *a, **k: _completed(stdout=data))

    result = probe("/renders/video.mp4")

    assert result is not None  # still parses, just with no duration/streams
    assert result.duration_seconds is None
    assert result.has_video_stream is False
    assert result.has_audio_stream is False

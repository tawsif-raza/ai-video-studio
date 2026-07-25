import subprocess

from execution_engine import ffmpeg_detector
from execution_engine.ffmpeg_detector import detect_ffmpeg

_VERSION_STDOUT = (
    "ffmpeg version 6.1.1 Copyright (c) 2000-2023 the FFmpeg developers\n"
    "built with gcc 13\n"
)


def _fake_completed(returncode=0, stdout=_VERSION_STDOUT):
    return subprocess.CompletedProcess(args=["ffmpeg", "-version"], returncode=returncode, stdout=stdout, stderr="")


def test_detect_available_parses_version(monkeypatch):
    monkeypatch.setattr(ffmpeg_detector.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_detector.subprocess, "run", lambda *a, **k: _fake_completed())

    info = detect_ffmpeg()

    assert info.available is True
    assert info.path == "/usr/bin/ffmpeg"
    assert info.version == "6.1.1"
    assert info.raw_version_line.startswith("ffmpeg version 6.1.1")


def test_detect_unavailable_when_not_on_path(monkeypatch):
    monkeypatch.setattr(ffmpeg_detector.shutil, "which", lambda _: None)

    info = detect_ffmpeg()

    assert info.available is False
    assert info.path is None
    assert info.version is None


def test_detect_unavailable_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(ffmpeg_detector.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(ffmpeg_detector.subprocess, "run", lambda *a, **k: _fake_completed(returncode=1))

    info = detect_ffmpeg()

    assert info.available is False
    assert info.path == "/usr/bin/ffmpeg"


def test_detect_unavailable_when_process_errors(monkeypatch):
    monkeypatch.setattr(ffmpeg_detector.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def _boom(*a, **k):
        raise OSError("cannot exec")

    monkeypatch.setattr(ffmpeg_detector.subprocess, "run", _boom)

    info = detect_ffmpeg()

    assert info.available is False
    assert info.path == "/usr/bin/ffmpeg"


def test_detect_handles_timeout(monkeypatch):
    monkeypatch.setattr(ffmpeg_detector.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ffmpeg -version", timeout=10)

    monkeypatch.setattr(ffmpeg_detector.subprocess, "run", _timeout)

    info = detect_ffmpeg()

    assert info.available is False

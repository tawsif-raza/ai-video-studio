import subprocess

import pytest

from execution_engine import ffmpeg_executor
from execution_engine.ffmpeg_executor import execute
from shared_core.contracts.render import FFmpegCommandSpec, FFmpegInput


def _spec(output_path) -> FFmpegCommandSpec:
    return FFmpegCommandSpec(
        global_args=["-y"],
        inputs=[FFmpegInput(path="/media/in.png", kind="image")],
        filter_complex="[0:v]scale=1920:1080[vout]",
        output_args=["-map", "[vout]", "-c:v", "libx264"],
        output_path=str(output_path),
    )


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=["ffmpeg"], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_run_that_writes(temp_output_bytes=b"fake video bytes", returncode=0):
    """Returns a fake subprocess.run replacement that writes to whatever path
    is the last argv element (the temp output path the executor computed),
    mimicking what ffmpeg would actually do."""
    def _run(argv, **kwargs):
        if temp_output_bytes is not None:
            from pathlib import Path
            Path(argv[-1]).write_bytes(temp_output_bytes)
        return _completed(returncode=returncode, stderr="")
    return _run


def test_successful_execution_renames_temp_to_final_output(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _fake_run_that_writes())

    result = execute(_spec(output_path), ffmpeg_path="ffmpeg")

    assert result.success is True
    assert result.dry_run is False
    assert result.exit_code == 0
    assert result.output_path == str(output_path)
    assert output_path.is_file()
    assert output_path.read_bytes() == b"fake video bytes"
    assert not (tmp_path / "video.part.mp4").exists()  # temp file gone after rename
    assert result.started_at is not None and result.finished_at is not None
    assert result.duration_seconds is not None and result.duration_seconds >= 0


def test_output_directory_created_if_absent(tmp_path, monkeypatch):
    output_path = tmp_path / "nested" / "renders" / "video.mp4"
    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _fake_run_that_writes())

    result = execute(_spec(output_path))

    assert result.success is True
    assert output_path.is_file()


def test_nonzero_exit_reports_failure_and_cleans_up_temp(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    monkeypatch.setattr(
        ffmpeg_executor.subprocess, "run",
        _fake_run_that_writes(temp_output_bytes=b"partial garbage", returncode=1),
    )

    result = execute(_spec(output_path))

    assert result.success is False
    assert result.exit_code == 1
    assert result.error_type == "ffmpeg_failed"
    assert "code 1" in result.error
    assert not output_path.exists()
    assert not (tmp_path / "video.part.mp4").exists()  # partial temp cleaned up


def test_stderr_captured_and_tailed_on_failure(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    long_stderr = "x" * 10_000

    def _run(argv, **kwargs):
        return _completed(returncode=1, stderr=long_stderr)

    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _run)

    result = execute(_spec(output_path))

    assert result.success is False
    assert len(result.stderr_tail) == ffmpeg_executor.STDERR_TAIL_CHARS
    assert result.stderr_tail == long_stderr[-ffmpeg_executor.STDERR_TAIL_CHARS:]


def test_zero_exit_but_no_output_file_is_still_a_failure(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    # ffmpeg reports success but never actually wrote anything
    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _fake_run_that_writes(temp_output_bytes=None, returncode=0))

    result = execute(_spec(output_path))

    assert result.success is False
    assert result.error_type == "ffmpeg_failed"
    assert "no output file" in result.error
    assert not output_path.exists()


def test_zero_exit_with_empty_output_file_is_still_a_failure(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _fake_run_that_writes(temp_output_bytes=b"", returncode=0))

    result = execute(_spec(output_path))

    assert result.success is False
    assert not output_path.exists()


def test_timeout_reports_failure_and_cleans_up_temp(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    temp_output = tmp_path / "video.part.mp4"

    def _run(argv, **kwargs):
        temp_output.write_bytes(b"partial")  # ffmpeg had started writing before the timeout
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"), output=None, stderr="stuck")

    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _run)

    result = execute(_spec(output_path), timeout_seconds=5)

    assert result.success is False
    assert result.error_type == "timeout"
    assert "5s" in result.error
    assert not temp_output.exists()
    assert not output_path.exists()


def test_spawn_failure_reports_failure(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"

    def _run(argv, **kwargs):
        raise OSError("no such file or directory: ffmpeg")

    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _run)

    result = execute(_spec(output_path))

    assert result.success is False
    assert result.error_type == "spawn_error"
    assert "Failed to start ffmpeg" in result.error


def test_executor_never_raises_it_always_returns_a_result(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"

    def _run(argv, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _run)

    result = execute(_spec(output_path))  # must not raise
    assert result.success is False


def test_temp_output_argv_replaces_final_argument_only(tmp_path, monkeypatch):
    output_path = tmp_path / "video.mp4"
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = list(argv)
        from pathlib import Path
        Path(argv[-1]).write_bytes(b"x")
        return _completed(returncode=0)

    monkeypatch.setattr(ffmpeg_executor.subprocess, "run", _run)

    execute(_spec(output_path), ffmpeg_path="/usr/bin/ffmpeg")

    argv = captured["argv"]
    assert argv[0] == "/usr/bin/ffmpeg"
    assert argv[-1] == str(tmp_path / "video.part.mp4")
    assert argv[-1] != str(output_path)  # never asks ffmpeg to write the final path directly


def test_command_spec_is_frozen():
    spec = _spec("/tmp/video.mp4")
    with pytest.raises(Exception):
        spec.output_path = "/tmp/other.mp4"

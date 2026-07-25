import argparse
import json

from execution_engine.controller import ExecutionEngineController
from execution_engine.errors import (
    ExecutionEnvironmentError,
    MediaAccessError,
    RenderError,
    RenderInputError,
)
from project_manager.manager import ProjectManager
from shared_core.contracts.render import RenderOptions

# Each pre-execution error category gets its own exit code so callers/scripts
# can tell a missing binary (2) from missing media (3) from a bad project
# state (4). A render that reached ffmpeg but failed there (non-zero exit,
# timeout, spawn failure) is reported via RenderResult, not an exception - see
# RENDER_FAILURE_EXIT_CODE. A render that succeeded but failed postflight
# validation (wrong duration/resolution/fps/missing stream) gets its own
# distinct code too - a process success is not the same outcome as an
# accepted, VIDEO_RENDERED-worthy file.
EXIT_CODES = {
    ExecutionEnvironmentError: 2,
    MediaAccessError: 3,
    RenderInputError: 4,
}
RENDER_FAILURE_EXIT_CODE = 5
VALIDATION_FAILURE_EXIT_CODE = 6


def _exit_code_for(error: RenderError) -> int:
    for error_type, code in EXIT_CODES.items():
        if isinstance(error, error_type):
            return code
    return 1


def main():
    parser = argparse.ArgumentParser(description="AI Video Studio - FFmpeg Execution Engine")
    parser.add_argument("--project-id", required=True, help="Project id at status EDIT_PLAN_READY")
    parser.add_argument("--resolution", default="1920x1080")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--crf", type=int, default=20)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--codec", default="libx264", help="Video codec (output -c:v)")
    parser.add_argument("--timeout", type=int, default=None, help="Render timeout in seconds")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build, validate, and print the command, but never invoke ffmpeg",
    )
    args = parser.parse_args()

    options = RenderOptions(
        resolution=args.resolution,
        fps=args.fps,
        crf=args.crf,
        preset=args.preset,
        video_codec=args.codec,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
    )

    controller = ExecutionEngineController(ProjectManager())
    try:
        _project, ffmpeg_info, command_spec, render_result, validation_report = controller.run(
            project_id=args.project_id, options=options
        )
    except RenderError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, indent=2))
        raise SystemExit(_exit_code_for(error))

    report = {
        "ffmpeg": json.loads(ffmpeg_info.model_dump_json()),
        "command": json.loads(command_spec.model_dump_json()),
        "argv_preview": command_spec.to_argv(ffmpeg_info.path or "ffmpeg"),
        "render": json.loads(render_result.model_dump_json()),
    }
    if validation_report is not None:
        report["validation"] = json.loads(validation_report.model_dump_json())
    if render_result.dry_run:
        report["note"] = "Dry run: command built and validated, ffmpeg was not invoked."
    print(json.dumps(report, indent=2))

    if not render_result.success:
        exit_code = RENDER_FAILURE_EXIT_CODE
    elif validation_report is not None and not validation_report.is_valid:
        exit_code = VALIDATION_FAILURE_EXIT_CODE
    else:
        exit_code = 0
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

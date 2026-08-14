"""
Developer-only CLI for the Video Generation Engine (ARCHITECTURE.md SS25,
Milestone V3), mirroring render_app.py's shape exactly: parse args, run one
engine call through its Python API, print a JSON report, exit with a
category-specific code.

Deliberately narrow (ARCHITECTURE.md SS25.16 item 5 / milestone scope
limits): selects exactly one project, one shot, and one provider, and
generates exactly that one clip. It is not a project-orchestration tool -
there is no "generate all shots" or "watch a project and generate as shots
become ready" mode here; that's explicitly out of scope for this milestone.

Example:
    python video_app.py --project proj_123 --scene 1 --shot 2 --provider google_veo
"""

import argparse
import json

from project_manager.manager import ProjectManager
from shared_core.contracts.video_generation import ShotMediaSelection, VideoGenerationOptions
from video_generation_engine.controller import VideoGenerationEngineController
from video_generation_engine.errors import (
    MediaAccessError,
    VideoGenerationEnvironmentError,
    VideoGenerationError,
    VideoGenerationInputError,
)

# Same "one exit code per pre-flight error category" convention render_app.py
# uses - lets a caller/script tell a bad project state from missing
# credentials from missing media without parsing stdout.
EXIT_CODES = {
    VideoGenerationEnvironmentError: 2,
    MediaAccessError: 3,
    VideoGenerationInputError: 4,
}
GENERATION_FAILURE_EXIT_CODE = 5
VALIDATION_FAILURE_EXIT_CODE = 6


def _exit_code_for(error: VideoGenerationError) -> int:
    for error_type, code in EXIT_CODES.items():
        if isinstance(error, error_type):
            return code
    return 1


def main():
    parser = argparse.ArgumentParser(
        description=(
            "AI Video Studio - Video Generation Engine developer CLI. "
            "Generates exactly ONE clip for one shot with one provider."
        )
    )
    parser.add_argument("--project", required=True, dest="project_id", help="Project id")
    parser.add_argument("--scene", type=int, required=True, help="scene_id of the shot to generate")
    parser.add_argument("--shot", type=int, required=True, help="shot_id (within --scene) to generate")
    parser.add_argument(
        "--provider", default="google_veo",
        help="Registered video_generation_engine provider name (default: google_veo)",
    )
    parser.add_argument("--aspect-ratio", default="9:16", dest="aspect_ratio")
    parser.add_argument(
        "--resolution", default=None,
        help="Provider-specific resolution string (e.g. '720p'/'1080p' for google_veo)",
    )
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seed-image", default=None, dest="seed_image_path", help="Path to an image-to-video seed frame")
    parser.add_argument("--timeout", type=int, default=None, dest="timeout_seconds", help="Wall-clock generation timeout in seconds")
    parser.add_argument("--poll-interval", type=int, default=10, dest="poll_interval_seconds")
    parser.add_argument("--max-poll-attempts", type=int, default=60, dest="max_poll_attempts")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Resolve, validate, and authenticate, but never actually call the provider",
    )
    args = parser.parse_args()

    options = VideoGenerationOptions(
        provider=args.provider,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        fps=args.fps,
        seed_image_path=args.seed_image_path,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        max_poll_attempts=args.max_poll_attempts,
    )
    selections = [ShotMediaSelection(scene_id=args.scene, shot_id=args.shot, mode="video")]

    controller = VideoGenerationEngineController(ProjectManager())
    try:
        _project, provider_info, results, validation_reports = controller.run(
            project_id=args.project_id, selections=selections, options=options,
        )
    except VideoGenerationError as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}, indent=2))
        raise SystemExit(_exit_code_for(error))

    report = {
        "provider": json.loads(provider_info.model_dump_json()),
        "results": [json.loads(r.model_dump_json()) for r in results],
        "validation_reports": [json.loads(r.model_dump_json()) for r in validation_reports],
    }
    if results and results[0].dry_run:
        report["note"] = "Dry run: request built, validated, and authenticated - the provider was never called."
    elif not results:
        report["note"] = "Nothing generated: the shot was not selected, or already has a valid clip from a prior run."
    print(json.dumps(report, indent=2))

    if not results:
        raise SystemExit(0)
    result = results[0]
    if not result.success:
        raise SystemExit(GENERATION_FAILURE_EXIT_CODE)
    if validation_reports and not validation_reports[0].is_valid:
        raise SystemExit(VALIDATION_FAILURE_EXIT_CODE)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

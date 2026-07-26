import argparse
import json

from project_manager.manager import ProjectManager
from publishing_engine.controller import PublishingEngineController

# Publish readiness is reportable data, never an exception (the same
# "reportable, not exceptional" convention every Publishing Engine module
# established) - there is no RenderError-style exit-code table here. The one
# exit code below simply distinguishes "ready to publish" from "not yet".
NOT_READY_EXIT_CODE = 1


def main():
    parser = argparse.ArgumentParser(description="AI Video Studio - Publishing Engine")
    parser.add_argument("--project-id", required=True, help="Project id at status VIDEO_RENDERED")
    parser.add_argument("--platform", default="youtube")
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Mark the assembled publish request as dry-run. This CLI only checks "
            "readiness (state/credentials/authentication) - it does not call "
            "upload() itself yet, so dry-run has no upload to skip here."
        ),
    )
    args = parser.parse_args()

    manager = ProjectManager()
    project = manager.load_project(args.project_id)
    readiness_request = manager.build_publish_readiness_request(project, platform=args.platform)

    try:
        publishing_plan = manager.load_publishing_plan(project)
    except (ValueError, FileNotFoundError):
        publishing_plan = None  # no Producer Package yet - readiness will already report this

    controller = PublishingEngineController()
    result = controller.run(
        readiness_request=readiness_request,
        publishing_plan=publishing_plan,
        dry_run=args.dry_run,
    )

    # Persistence is deliberately kept separate from the controller (which
    # never touches project_manager) - the CLI runs the controller, then
    # hands its result here to be written to disk (Milestone P6).
    manager.save_publish_report(project, result)

    print(json.dumps(json.loads(result.model_dump_json()), indent=2))

    raise SystemExit(0 if result.ready_to_publish else NOT_READY_EXIT_CODE)


if __name__ == "__main__":
    main()

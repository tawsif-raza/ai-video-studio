import json

from project_manager.manager import ProjectManager
from utils.logger import get_logger
from web_api.run_registry import RunRegistry

logger = get_logger("web_api.publish_runner")


def run_publish_pipeline(
    *,
    run_id: str,
    project_id: str,
    project_manager: ProjectManager,
    run_registry: RunRegistry,
    controller_factory,
    platform: str,
    dry_run: bool,
) -> None:
    """Background-task entry point for POST /projects/{id}/publish/run.
    Mirrors run_director_pipeline (W2) / run_producer_pipeline (W3) /
    run_render_pipeline (W4): the unmodified controller, run-registry
    bookkeeping, an exception boundary that catches SystemExit first and
    explicitly (defensive - PublishingEngineController never actually
    raises it, same as ExecutionEngineController in W4; only publish_app.py's
    CLI wrapper does, via `raise SystemExit(0 if result.ready_to_publish
    else NOT_READY_EXIT_CODE)`).

    Reproduces exactly what publish_app.py does and nothing more:
    build_publish_readiness_request + load_publishing_plan (both existing,
    unmodified ProjectManager methods) assemble the controller's typed
    input; controller.run() performs readiness + credential + real
    authentication checks; save_publish_report persists the result. No
    upload is triggered - PublishingEngineController.run() doesn't perform
    one (its own docstring: "It never uploads... Those all remain later
    milestones' jobs"), and WEB_DASHBOARD_ARCHITECTURE.md SS12 explicitly
    keeps real upload-triggering out of scope for the dashboard. A
    ready_to_publish=False outcome is not a failure to report here - it's
    the same "reportable, not exceptional" verdict publish_app.py's own
    non-zero-but-not-crashing exit code already treats it as; the Run is
    SUCCEEDED with the verdict visible in its result, mirroring W3/W4's
    identical treatment of an invalid asset manifest / a failed render."""
    run_registry.mark_running(run_id)
    controller = controller_factory()

    try:
        project = project_manager.load_project(project_id)
        readiness_request = project_manager.build_publish_readiness_request(project, platform=platform)
        try:
            publishing_plan = project_manager.load_publishing_plan(project)
        except (ValueError, FileNotFoundError):
            publishing_plan = None  # no Producer Package yet - readiness will already report this

        result = controller.run(
            readiness_request=readiness_request, publishing_plan=publishing_plan, dry_run=dry_run
        )
        project_manager.save_publish_report(project, result)
        result_dict = json.loads(result.model_dump_json())
    except SystemExit as exc:
        logger.error(f"Publish run {run_id} (project {project_id}) raised SystemExit({exc.code})")
        run_registry.mark_failed(run_id, error="Publishing pipeline exited unexpectedly - see server logs")
        return
    except Exception as exc:
        logger.exception(f"Publish run {run_id} (project {project_id}) failed with an unexpected exception")
        run_registry.mark_failed(run_id, error=str(exc))
        return

    run_registry.mark_succeeded(run_id, result=result_dict)

import json

from project_manager.manager import ProjectManager
from utils.logger import get_logger
from web_api.run_registry import RunRegistry

logger = get_logger("web_api.producer_runner")


def run_producer_pipeline(
    *,
    run_id: str,
    project_id: str,
    project_manager: ProjectManager,
    run_registry: RunRegistry,
    controller_factory,
) -> None:
    """Background-task entry point for POST /projects/{id}/producer/run.
    Mirrors run_director_pipeline's shape exactly (W2): unmodified
    controller, run-registry bookkeeping, SystemExit caught first and
    explicitly since it's a BaseException a bare `except Exception` would
    miss.

    Unlike Director Studio, ProducerStudioController needs no LLM client
    and no _PreCreatedProjectManager delegate - it loads an *existing*
    project by project_id itself (producer_studio/controller.py line 40),
    so there is no project-creation race to work around here."""
    run_registry.mark_running(run_id)
    controller = controller_factory(project_manager)

    try:
        (
            project,
            manifest,
            timeline,
            subtitle_plan,
            music_plan,
            editing_plan,
            thumbnail_plan,
            publishing_plan,
        ) = controller.run(project_id=project_id)

        # Same report shape producer_app.py already prints to stdout - reused
        # here as-is, per the "Run.result is exactly what the CLI would have
        # printed" convention established in W2.
        result = {"asset_validation": json.loads(manifest.model_dump_json())}
        if timeline is not None:
            result["timeline"] = json.loads(timeline.model_dump_json())
        if subtitle_plan is not None:
            result["subtitles"] = json.loads(subtitle_plan.model_dump_json())
        if music_plan is not None:
            result["music"] = json.loads(music_plan.model_dump_json())
        if editing_plan is not None:
            result["editing"] = json.loads(editing_plan.model_dump_json())
        if thumbnail_plan is not None:
            result["thumbnail"] = json.loads(thumbnail_plan.model_dump_json())
        if publishing_plan is not None:
            result["publishing"] = json.loads(publishing_plan.model_dump_json())
    except SystemExit as exc:
        logger.error(
            f"Producer Studio run {run_id} (project {project_id}) failed - "
            f"a pipeline stage reported failure (exit code {exc.code})"
        )
        run_registry.mark_failed(
            run_id,
            error="Producer Studio pipeline failed - see server logs for the failing stage",
        )
        return
    except Exception as exc:
        logger.exception(
            f"Producer Studio run {run_id} (project {project_id}) failed with an unexpected exception"
        )
        run_registry.mark_failed(run_id, error=str(exc))
        return

    # An asset manifest that failed validation is a reported outcome, not a
    # controller failure (ProducerStudioController returns normally with
    # manifest.is_valid=False rather than raising) - mirrored here as a
    # SUCCEEDED run whose result makes that verdict visible, not a FAILED
    # run. This matches the "reportable, not exceptional" convention
    # ARCHITECTURE.md SS2 already applies to RenderResult/RenderValidationReport.
    run_registry.mark_succeeded(run_id, result=result)

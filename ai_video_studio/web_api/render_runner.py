import json

from execution_engine.errors import RenderError
from project_manager.manager import ProjectManager
from shared_core.contracts.render import RenderOptions
from utils.logger import get_logger
from web_api.run_registry import RunRegistry

logger = get_logger("web_api.render_runner")


def run_render_pipeline(
    *,
    run_id: str,
    project_id: str,
    project_manager: ProjectManager,
    run_registry: RunRegistry,
    controller_factory,
    options: RenderOptions,
) -> None:
    """Background-task entry point for POST /projects/{id}/render/run.
    Mirrors run_director_pipeline (W2) / run_producer_pipeline (W3): the
    unmodified ExecutionEngineController, run-registry bookkeeping, and an
    exception boundary - but this controller's real failure shape differs
    from Director/Producer Studio's, so the boundary here is not a copy of
    theirs:

    - execution_engine/controller.py never raises SystemExit itself - it
      raises a RenderError subclass (ExecutionEnvironmentError,
      MediaAccessError, RenderInputError) for anything wrong before
      execution can even be attempted. SystemExit is still caught first and
      explicitly, ahead of RenderError and the generic Exception fallback,
      per this milestone's requirement and for consistency with the W2/W3
      boundary shape - defensive, since render_app.py's *CLI* wrapper is
      the thing that actually raises SystemExit today, not the controller.
    - An execution-phase or postflight-validation failure (ffmpeg exited
      non-zero, or the rendered file didn't match its expected profile) is
      never an exception at all - render_result/validation_report are
      always returned data (execution_engine/errors.py's own docstring).
      Mirroring W3's identical treatment of an invalid asset manifest, this
      is a SUCCEEDED run whose result makes the failure verdict visible,
      not a FAILED run - the render *request* completed; the render
      *output* didn't pass."""
    run_registry.mark_running(run_id)
    controller = controller_factory(project_manager)

    try:
        project, ffmpeg_info, command_spec, render_result, validation_report = controller.run(
            project_id=project_id, options=options
        )
        result = {
            "ffmpeg": json.loads(ffmpeg_info.model_dump_json()),
            "render": json.loads(render_result.model_dump_json()),
        }
        if validation_report is not None:
            result["validation"] = json.loads(validation_report.model_dump_json())
    except SystemExit as exc:
        logger.error(f"Render run {run_id} (project {project_id}) raised SystemExit({exc.code})")
        run_registry.mark_failed(run_id, error="Render pipeline exited unexpectedly - see server logs")
        return
    except RenderError as exc:
        logger.error(f"Render run {run_id} (project {project_id}) failed before execution: {exc}")
        run_registry.mark_failed(run_id, error=f"{type(exc).__name__}: {exc}")
        return
    except Exception as exc:
        logger.exception(f"Render run {run_id} (project {project_id}) failed with an unexpected exception")
        run_registry.mark_failed(run_id, error=str(exc))
        return

    run_registry.mark_succeeded(run_id, result=result)

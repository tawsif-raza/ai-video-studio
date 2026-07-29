import json
from typing import Optional

from project_manager.manager import ProjectManager
from project_manager.project import Project
from utils.logger import get_logger
from web_api.run_registry import RunRegistry

logger = get_logger("web_api.director_runner")


class _PreCreatedProjectManager:
    """Thin delegate, not a new implementation of ProjectManager: forwards
    every call to the real ProjectManager unchanged except create_project(),
    which hands back an already-created Project instead of creating a new
    one.

    Why this exists: DirectorStudioController.run() creates its own project
    as its very first statement (director_studio/controller.py line 63) and
    has no parameter to accept an existing one - by design, that's how the
    CLI has always worked, and this milestone must not change Director
    Studio's signature to accommodate the API. But a 202 response needs to
    return the real project_id immediately, before the (potentially slow,
    LLM-backed) rest of the run has even started. So the API layer creates
    the project itself, synchronously, in the request handler - a cheap
    local file write, no LLM call - and hands this delegate to the
    controller so its internal create_project() call resolves to that same
    project instead of allocating a second, different one. Every other
    method call (save_story_plan, export_production_package, etc.) still
    goes straight through to the real ProjectManager, exactly as if the
    controller had been given it directly."""

    def __init__(self, delegate: ProjectManager, precreated_project: Project):
        self._delegate = delegate
        self._project = precreated_project

    def create_project(self) -> Project:
        return self._project

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def run_director_pipeline(
    *,
    run_id: str,
    project: Project,
    project_manager: ProjectManager,
    run_registry: RunRegistry,
    idea: str,
    duration: int,
    tone: Optional[str],
    audience: Optional[str],
    art_style: Optional[str],
    skip_research: bool,
    llm_client_factory,
    controller_factory,
) -> None:
    """Background-task entry point for POST /projects. Runs the unmodified
    controller exactly as app.py does - same llm client type, same
    ProjectManager (via the delegate above), same call signature - wrapped
    only in run-registry bookkeeping and an exception boundary.

    That boundary is the one thing a CLI process never needed and a
    long-lived API worker cannot survive without:
    director_studio/controller.py raises SystemExit(1) on any stage
    failure. SystemExit is a BaseException, not an Exception, so it is
    caught explicitly and first here - a bare `except Exception` would let
    it propagate straight out of this background task and, unhandled,
    through FastAPI's background-task runner."""
    run_registry.mark_running(run_id)
    llm = llm_client_factory()
    wrapped_pm = _PreCreatedProjectManager(project_manager, project)
    controller = controller_factory(llm, wrapped_pm)

    try:
        controller.run(
            idea=idea,
            duration=duration,
            tone=tone,
            audience=audience,
            art_style=art_style,
            skip_research=skip_research,
        )
        # Same convention app.py's stdout output follows: the "result" of a
        # successful run is the PromptSet the pipeline produced. Reloaded
        # through the real, unwrapped ProjectManager rather than captured
        # from the controller (which returns nothing) - reused exactly as
        # producer_app.py already reloads it to start the next stage.
        final_project = project_manager.load_project(project.project_id)
        prompt_set = project_manager.load_prompt_set(final_project)
        result = json.loads(prompt_set.model_dump_json())
    except SystemExit as exc:
        logger.error(
            f"Director Studio run {run_id} (project {project.project_id}) "
            f"failed - a pipeline stage reported failure (exit code {exc.code})"
        )
        run_registry.mark_failed(
            run_id,
            error="Director Studio pipeline failed - see server logs for the failing stage",
        )
        return
    except Exception as exc:
        logger.exception(
            f"Director Studio run {run_id} (project {project.project_id}) "
            f"failed with an unexpected exception"
        )
        run_registry.mark_failed(run_id, error=str(exc))
        return

    run_registry.mark_succeeded(run_id, result=result)

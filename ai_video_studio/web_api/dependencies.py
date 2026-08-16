from functools import lru_cache

from fastapi import Request

from director_studio.controller import DirectorStudioController
from execution_engine.controller import ExecutionEngineController
from llm.failover_client import FailoverLLMClient as LLMClient
from producer_studio.controller import ProducerStudioController
from project_manager.manager import ProjectManager
from publishing_engine.controller import PublishingEngineController
from web_api.run_registry import RunRegistry
from web_api.sse import DEFAULT_POLL_INTERVAL_SECONDS


@lru_cache
def get_project_manager() -> ProjectManager:
    """One ProjectManager instance per process, exactly like each CLI
    constructs exactly one (app.py, producer_app.py, render_app.py,
    publish_app.py). ProjectManager itself holds no per-request state - it
    reads settings.OUTPUT_DIR fresh on every call - so a single cached
    instance is safe to share across all requests and, in tests, across
    OUTPUT_DIR monkeypatches too."""
    return ProjectManager()


def get_run_registry(request: Request) -> RunRegistry:
    """Unlike get_project_manager, deliberately NOT a process-wide
    lru_cache singleton: the registry is created once per app instance in
    create_app() (web_api/__init__.py) and stored on app.state, so every
    TestClient(create_app()) in tests gets its own isolated registry
    instead of leaking Run objects across unrelated test cases."""
    return request.app.state.run_registry


def get_llm_client_factory():
    """Returns the same LLM client class app.py already uses
    (llm.failover_client.FailoverLLMClient) - a factory, not an instance, so
    each Director Studio run gets its own client the same way app.py's
    main() does. Overridden in tests via app.dependency_overrides to inject
    a fake LLM client without touching Director Studio."""
    return LLMClient


def get_director_controller_factory():
    """Returns the unmodified DirectorStudioController class. Overridden in
    tests that need to exercise the API boundary's SystemExit/exception
    handling deterministically, without depending on real agent/LLM
    behavior to produce a failure."""
    return DirectorStudioController


def get_producer_controller_factory():
    """Returns the unmodified ProducerStudioController class. Overridden in
    tests the same way get_director_controller_factory is."""
    return ProducerStudioController


def get_execution_controller_factory():
    """Returns the unmodified ExecutionEngineController class, called as
    controller_factory(project_manager) exactly like the other two
    factories - detector/executor/prober all default to the real
    ffmpeg-backed implementations (execution_engine/controller.py), never
    reimplemented here. Overridden in tests with a callable that injects
    fake detector/executor/prober (the same seam
    tests/integration/test_render_pipeline.py already uses) so render
    behavior can be exercised deterministically without a real ffmpeg
    binary."""
    return ExecutionEngineController


def get_publish_controller_factory():
    """Returns the unmodified PublishingEngineController class - called as
    controller_factory() with NO arguments (unlike the producer/execution
    factories), because PublishingEngineController.__init__ takes only
    keyword-only args that all default (platform_resolver, readiness_check,
    credential_provider, auth_cache) and never accepts a project_manager;
    it never imports project_manager at all (publishing_engine/controller.py's
    own docstring: "It still never imports project_manager"). Overridden in
    tests with a callable that injects fake platform_resolver/
    readiness_check/credential_provider/auth_cache, the same seam
    tests/test_publishing_controller.py already uses."""
    return PublishingEngineController


def get_sse_poll_interval() -> float:
    """How often web_api/sse.py's run_events() polls RunRegistry.get() for
    a status change. A plain float, not a class/instance - overridden in
    tests to a much smaller value so streaming tests don't have to wait
    out a production-scale interval to observe a transition."""
    return DEFAULT_POLL_INTERVAL_SECONDS

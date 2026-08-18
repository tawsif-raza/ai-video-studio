import pytest
from fastapi.testclient import TestClient

from config import settings
from execution_engine.errors import RenderInputError
from project_manager.project import ProjectState
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.prompt_set import PromptSet
from shared_core.contracts.publish import AuthenticationResult, PublishValidationCheck, PublishValidationReport, ReadyToPublishResult
from shared_core.contracts.render import FFmpegInfo, RenderResult, RenderValidationReport
from web_api import create_app
from web_api.dependencies import (
    get_director_controller_factory,
    get_execution_controller_factory,
    get_llm_client_factory,
    get_producer_controller_factory,
    get_publish_controller_factory,
)


class FakeLLMClient:
    model_name = "fake-llm"


class SucceedingDirectorController:
    """Stands in for DirectorStudioController: performs just enough real
    ProjectManager writes (via the injected delegate) for the API's
    post-run reload to succeed, without running any real agents or LLM
    calls. The real controller is exercised separately in
    tests/integration/test_api_director_pipeline.py."""

    def __init__(self, llm_client, project_manager):
        self.project_manager = project_manager

    def run(self, *, idea, duration, tone, audience, art_style, skip_research, scene_count_mode="default", scene_count=None):
        project = self.project_manager.create_project()
        self.project_manager.save_prompt_set(project, PromptSet())


class FailingDirectorController:
    """Reproduces Director Studio's real failure signal - SystemExit(1) -
    without needing a real agent failure to trigger it."""

    def __init__(self, llm_client, project_manager):
        pass

    def run(self, **kwargs):
        raise SystemExit(1)


class CrashingDirectorController:
    """Raises a plain, non-SystemExit exception."""

    def __init__(self, llm_client, project_manager):
        pass

    def run(self, **kwargs):
        raise RuntimeError("boom")


class SucceedingProducerController:
    """Stands in for ProducerStudioController: returns the same 8-tuple
    shape the real controller returns, with a valid asset manifest and
    every later stage left None (as the real controller itself would leave
    them when called on a project with no media - here just kept minimal
    since these router-level tests exercise the API/registry mechanics,
    not planning-stage correctness. The real controller, unmocked, is
    exercised in tests/integration/test_api_producer_pipeline.py."""

    def __init__(self, project_manager):
        self.project_manager = project_manager

    def run(self, *, project_id):
        project = self.project_manager.load_project(project_id)
        manifest = ValidatedAssetManifest(is_valid=True)
        return project, manifest, None, None, None, None, None, None


class FailingProducerController:
    """Reproduces Producer Studio's real failure signal - SystemExit(1)."""

    def __init__(self, project_manager):
        pass

    def run(self, **kwargs):
        raise SystemExit(1)


class CrashingProducerController:
    """Raises a plain, non-SystemExit exception."""

    def __init__(self, project_manager):
        pass

    def run(self, **kwargs):
        raise RuntimeError("boom")


class SucceedingExecutionController:
    """Stands in for ExecutionEngineController: returns the same 5-tuple
    shape the real controller returns, with a fully successful render and
    passing postflight validation. The real controller, unmocked (with a
    fake detector/executor/prober, the same seam
    tests/integration/test_render_pipeline.py already uses), is exercised
    in tests/integration/test_api_render_pipeline.py."""

    def __init__(self, project_manager):
        self.project_manager = project_manager

    def run(self, *, project_id, options=None):
        project = self.project_manager.load_project(project_id)
        ffmpeg_info = FFmpegInfo(available=True, path="/usr/bin/ffmpeg", version="6.1.1")
        render_result = RenderResult(
            success=True, dry_run=False, output_path="/tmp/out.mp4", exit_code=0, duration_seconds=1.0
        )
        validation_report = RenderValidationReport(is_valid=True, checks=[], output_path="/tmp/out.mp4")
        return project, ffmpeg_info, None, render_result, validation_report


class FailedRenderExecutionController:
    """Reproduces the real controller's "returned data, not an exception"
    failure shape: ffmpeg ran but exited non-zero. No postflight report,
    exactly like the real controller when render_result.success is False
    (execution_engine/controller.py only probes on success)."""

    def __init__(self, project_manager):
        self.project_manager = project_manager

    def run(self, *, project_id, options=None):
        project = self.project_manager.load_project(project_id)
        ffmpeg_info = FFmpegInfo(available=True, path="/usr/bin/ffmpeg", version="6.1.1")
        render_result = RenderResult(
            success=False, dry_run=False, exit_code=1, error="ffmpeg exited with code 1", error_type="ffmpeg_failed"
        )
        return project, ffmpeg_info, None, render_result, None


class RenderErrorExecutionController:
    """Reproduces the real controller's real, documented exception type for
    anything wrong before execution can even be attempted."""

    def __init__(self, project_manager):
        pass

    def run(self, **kwargs):
        raise RenderInputError("Producer Package inputs are inconsistent")


class SystemExitExecutionController:
    """Defensive-boundary test double: the real controller never actually
    raises SystemExit (only render_app.py's CLI wrapper does, after
    catching a RenderError) - this exists to prove the API boundary
    survives it anyway, per this milestone's explicit requirement."""

    def __init__(self, project_manager):
        pass

    def run(self, **kwargs):
        raise SystemExit(1)


class CrashingExecutionController:
    """Raises a plain, non-SystemExit, non-RenderError exception."""

    def __init__(self, project_manager):
        pass

    def run(self, **kwargs):
        raise RuntimeError("boom")


class SucceedingPublishController:
    """Stands in for PublishingEngineController: readiness, credentials,
    and authentication all pass. Constructed with NO arguments, exactly
    like the real controller's own __init__ (all keyword-only, all
    defaulted) - it never receives project_manager. The real controller,
    unmocked (with a fake platform_resolver/credential_provider, the same
    seam tests/test_publishing_controller.py already uses), is exercised
    in tests/integration/test_api_publish_pipeline.py."""

    def __init__(self):
        pass

    def run(self, *, readiness_request, publishing_plan=None, dry_run=True):
        ok_report = PublishValidationReport(is_valid=True, platform=readiness_request.platform, checks=[])
        return ReadyToPublishResult(
            platform=readiness_request.platform,
            dry_run=dry_run,
            readiness=ok_report,
            credentials=ok_report,
            authentication=AuthenticationResult(
                success=True, platform=readiness_request.platform, account_label="Test Channel"
            ),
            ready_to_publish=True,
            request=None,
        )


class NotReadyPublishController:
    """Reproduces the real controller's "returned data, not an exception"
    outcome: readiness fails (e.g. no rendered video yet), so
    ready_to_publish=False - never raised, mirroring
    publishing_engine/controller.py's own "reportable, not exceptional"
    design (ReadyToPublishResult is always returned, success or not)."""

    def __init__(self):
        pass

    def run(self, *, readiness_request, publishing_plan=None, dry_run=True):
        failing_readiness = PublishValidationReport(
            is_valid=False,
            platform=readiness_request.platform,
            checks=[PublishValidationCheck(
                name="video_present", passed=False, expected="a rendered video file", actual="none found"
            )],
        )
        ok_credentials = PublishValidationReport(is_valid=True, platform=readiness_request.platform, checks=[])
        return ReadyToPublishResult(
            platform=readiness_request.platform,
            dry_run=dry_run,
            readiness=failing_readiness,
            credentials=ok_credentials,
            authentication=AuthenticationResult(success=True, platform=readiness_request.platform),
            ready_to_publish=False,
            request=None,
        )


class SystemExitPublishController:
    """Defensive-boundary test double: the real controller never actually
    raises SystemExit (only publish_app.py's CLI wrapper does, after
    inspecting result.ready_to_publish) - this exists to prove the API
    boundary survives it anyway, per this milestone's explicit requirement."""

    def __init__(self):
        pass

    def run(self, **kwargs):
        raise SystemExit(1)


class CrashingPublishController:
    """Raises a plain, non-SystemExit exception."""

    def __init__(self):
        pass

    def run(self, **kwargs):
        raise RuntimeError("boom")


@pytest.fixture
def app_(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    app = create_app()
    app.dependency_overrides[get_llm_client_factory] = lambda: FakeLLMClient
    return app


@pytest.fixture
def client(app_):
    return TestClient(app_)


def post_with_controller(client, app_, controller, body=None):
    app_.dependency_overrides[get_director_controller_factory] = lambda: controller
    return client.post("/projects", json=body or {"idea": "A brave explorer"})


def post_producer_run(client, app_, controller, project_id):
    app_.dependency_overrides[get_producer_controller_factory] = lambda: controller
    return client.post(f"/projects/{project_id}/producer/run")


def post_render_run(client, app_, controller, project_id, body=None):
    app_.dependency_overrides[get_execution_controller_factory] = lambda: controller
    return client.post(f"/projects/{project_id}/render/run", json=body or {})


def post_publish_run(client, app_, controller, project_id, body=None):
    app_.dependency_overrides[get_publish_controller_factory] = lambda: controller
    return client.post(f"/projects/{project_id}/publish/run", json=body or {})


def make_edit_plan_ready_project(project_manager):
    """Router-level render tests only need a project whose status satisfies
    the router's own EDIT_PLAN_READY precondition check - not a real,
    fully-planned Producer Package (that's what
    tests/integration/test_api_render_pipeline.py exercises with the real
    controller). Uses ProjectManager's own state-transition primitive
    directly, the same way tests/project_manager/test_manager.py already
    does, rather than duplicating the full real Director+Producer flow
    just to reach one status value."""
    project = project_manager.create_project()
    return project_manager._advance(project, status=ProjectState.EDIT_PLAN_READY)


def make_video_rendered_project(project_manager):
    """Same convention as make_edit_plan_ready_project, one status further -
    router-level publish tests only need VIDEO_RENDERED to satisfy the
    router's own eligibility gate, not a real render. The real end-to-end
    flow is exercised in tests/integration/test_api_publish_pipeline.py."""
    project = project_manager.create_project()
    return project_manager._advance(project, status=ProjectState.VIDEO_RENDERED)

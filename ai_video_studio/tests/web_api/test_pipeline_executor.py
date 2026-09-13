"""Phase 1.1 P0 fix regression tests (docs/phase1.1-p0-fixes.md, Fix 6).

Tests A-E and G/I exercise PipelineExecutor directly against a plain
RunRegistry - fast, deterministic, no HTTP/ASGI overhead, using
ControllableRunner (a run_*_pipeline-shaped callable under full test
control via threading.Event, matching exactly how the real
director_runner.py/producer_runner.py/render_runner.py/publish_runner.py
functions behave: mark_running -> do the work -> mark_succeeded/failed).

Tests F and H go through the real FastAPI app (create_app(), a real
TestClient, real concurrent OS threads issuing real HTTP requests) because
they specifically claim something about the whole wired system - that GET
/health stays fast, and that the cap is genuinely global across different
projects/users - not just about PipelineExecutor in isolation.
"""
import concurrent.futures as cf
import threading
import time

from fastapi.testclient import TestClient

from config import settings
from shared_core.contracts.prompt_set import PromptSet
from tests.web_api.conftest import FakeLLMClient
from web_api import create_app
from web_api.dependencies import (
    get_director_controller_factory,
    get_llm_client_factory,
    get_producer_controller_factory,
)
from web_api.pipeline_executor import PipelineExecutor
from web_api.run_registry import RunRegistry, RunStatus


class ControllableRunner:
    """A run_*_pipeline-shaped callable (matches the
    fn(*, run_id, run_registry, **kwargs) signature PipelineExecutor.submit
    calls) whose execution is entirely under test control: marks RUNNING
    and signals `entered`, blocks on `release` until the test lets it
    proceed, then marks SUCCEEDED or FAILED via the real RunRegistry
    methods - exactly what a real runner function does, just with the
    "do the actual work" step replaced by a controllable wait."""

    def __init__(self, *, fail: bool = False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.completed = threading.Event()
        self.fail = fail

    def __call__(self, *, run_id, run_registry, **kwargs) -> None:
        run_registry.mark_running(run_id)
        self.entered.set()
        self.release.wait(timeout=10)
        if self.fail:
            run_registry.mark_failed(run_id, error="boom")
        else:
            run_registry.mark_succeeded(run_id, result={"ok": True})
        self.completed.set()


def _wait_until(predicate, timeout=2.0, interval=0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --- Test A ---------------------------------------------------------------

def test_a_single_pipeline_run_succeeds():
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=2, run_timeout_seconds=5.0)
    runner = ControllableRunner()
    run = registry.start_run(project_id="p1", stage="director")

    executor.submit(run_id=run.run_id, run_registry=registry, fn=runner)
    assert runner.entered.wait(timeout=2)
    runner.release.set()
    assert runner.completed.wait(timeout=2)

    assert _wait_until(lambda: executor.active_count() == 0)
    assert registry.get(run.run_id).status == RunStatus.SUCCEEDED


# --- Test B ---------------------------------------------------------------

def test_b_excess_runs_queue_behind_the_configured_maximum():
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=2, run_timeout_seconds=5.0)
    runners = [ControllableRunner() for _ in range(5)]
    runs = [registry.start_run(project_id=f"p{i}", stage="director") for i in range(5)]

    for run, runner in zip(runs, runners):
        executor.submit(run_id=run.run_id, run_registry=registry, fn=runner)

    def entered_count():
        return sum(1 for r in runners if r.entered.is_set())

    assert _wait_until(lambda: entered_count() == 2, timeout=2.0), "expected exactly max_workers to start"
    # Held steady for a further window - proves the other 3 are genuinely
    # queued (never started), not merely "not yet scheduled".
    time.sleep(0.3)
    assert entered_count() == 2, "PipelineExecutor must not run more than max_workers concurrently"

    for runner in runners:
        runner.release.set()
    for runner in runners:
        assert runner.entered.wait(timeout=3)
        assert runner.completed.wait(timeout=3)
    for run in runs:
        assert registry.get(run.run_id).status == RunStatus.SUCCEEDED


# --- Test C ---------------------------------------------------------------

def test_c_a_failed_run_releases_its_concurrency_slot():
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=1, run_timeout_seconds=5.0)
    failing = ControllableRunner(fail=True)
    run1 = registry.start_run(project_id="p1", stage="director")

    executor.submit(run_id=run1.run_id, run_registry=registry, fn=failing)
    assert failing.entered.wait(timeout=2)
    failing.release.set()
    assert failing.completed.wait(timeout=2)
    assert registry.get(run1.run_id).status == RunStatus.FAILED

    succeeding = ControllableRunner()
    run2 = registry.start_run(project_id="p2", stage="director")
    executor.submit(run_id=run2.run_id, run_registry=registry, fn=succeeding)

    assert succeeding.entered.wait(timeout=2), "slot was not released after a failed run"
    succeeding.release.set()
    assert succeeding.completed.wait(timeout=2)
    assert registry.get(run2.run_id).status == RunStatus.SUCCEEDED


# --- Test D ---------------------------------------------------------------

def test_d_cancelling_a_queued_run_prevents_it_from_ever_starting():
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=1, run_timeout_seconds=5.0)
    occupying = ControllableRunner()
    never_should_run = ControllableRunner()

    run1 = registry.start_run(project_id="p1", stage="director")
    executor.submit(run_id=run1.run_id, run_registry=registry, fn=occupying)
    assert occupying.entered.wait(timeout=2)

    run2 = registry.start_run(project_id="p2", stage="director")
    executor.submit(run_id=run2.run_id, run_registry=registry, fn=never_should_run)

    assert executor.cancel(run2.run_id, registry) is True
    assert registry.get(run2.run_id).status == RunStatus.CANCELLED

    occupying.release.set()
    assert occupying.completed.wait(timeout=2)

    # Give the pool every chance to have started run2 if cancellation had
    # failed to actually prevent it.
    time.sleep(0.3)
    assert never_should_run.entered.is_set() is False, "a cancelled run must never execute"


def test_d_cancelling_an_already_running_run_is_a_documented_no_op():
    """PipelineExecutor.cancel can only ever prevent a not-yet-started run
    (see its docstring) - Python has no safe way to stop a thread already
    executing arbitrary code. Calling cancel on one already RUNNING must
    return False and must NOT relabel it CANCELLED - that would be a lie
    this architecture cannot back up."""
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=1, run_timeout_seconds=5.0)
    running = ControllableRunner()
    run = registry.start_run(project_id="p1", stage="director")
    executor.submit(run_id=run.run_id, run_registry=registry, fn=running)
    assert running.entered.wait(timeout=2)

    assert executor.cancel(run.run_id, registry) is False
    assert registry.get(run.run_id).status == RunStatus.RUNNING

    running.release.set()
    assert running.completed.wait(timeout=2)


# --- Test E -----------------------------------------------------------------

def test_e_a_timed_out_run_releases_its_concurrency_slot_and_late_results_are_discarded():
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=1, run_timeout_seconds=0.2)
    stuck = ControllableRunner()  # .release is never set - simulates a genuinely hung stage
    run1 = registry.start_run(project_id="p1", stage="director")

    executor.submit(run_id=run1.run_id, run_registry=registry, fn=stuck)
    assert stuck.entered.wait(timeout=2)

    assert _wait_until(lambda: registry.get(run1.run_id).status == RunStatus.TIMED_OUT, timeout=2.0)
    assert registry.get(run1.run_id).error is not None

    # The slot must be free for a new run even though `stuck` is (by
    # design - see PipelineExecutor's documented limitation) still running
    # in the background.
    succeeding = ControllableRunner()
    run2 = registry.start_run(project_id="p2", stage="director")
    executor.submit(run_id=run2.run_id, run_registry=registry, fn=succeeding)
    assert succeeding.entered.wait(timeout=2), "concurrency slot was not released after a timeout"
    succeeding.release.set()
    assert succeeding.completed.wait(timeout=2)
    assert registry.get(run2.run_id).status == RunStatus.SUCCEEDED

    # Documented limitation, proven directly: letting the stuck run's
    # underlying thread finish late must NOT overwrite the already-recorded
    # TIMED_OUT verdict (RunRegistry._finish's idempotency guard).
    stuck.release.set()
    assert stuck.completed.wait(timeout=2)
    time.sleep(0.05)
    assert registry.get(run1.run_id).status == RunStatus.TIMED_OUT


# --- Test G -----------------------------------------------------------------

def test_g_a_stuck_heavy_run_cannot_block_the_queue_forever():
    """A legitimately-large (here: a run that never voluntarily finishes)
    request must not be able to occupy the execution system indefinitely
    and starve everyone queued behind it - PipelineExecutor's wall-clock
    timeout (Fix 3) is what guarantees this, not the concurrency cap
    (Fix 1) alone."""
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=1, run_timeout_seconds=0.2)
    stuck = ControllableRunner()  # never releases
    followers = [ControllableRunner() for _ in range(3)]

    stuck_run = registry.start_run(project_id="p-stuck", stage="director")
    executor.submit(run_id=stuck_run.run_id, run_registry=registry, fn=stuck)
    follower_runs = [registry.start_run(project_id=f"p{i}", stage="director") for i in range(3)]
    for run, runner in zip(follower_runs, followers):
        executor.submit(run_id=run.run_id, run_registry=registry, fn=runner)
        runner.release.set()  # each can finish instantly once actually scheduled

    for run in follower_runs:
        assert _wait_until(
            lambda r=run: registry.get(r.run_id).status == RunStatus.SUCCEEDED, timeout=3.0
        ), "a stuck run ahead in the queue must not permanently starve runs queued behind it"

    assert registry.get(stuck_run.run_id).status == RunStatus.TIMED_OUT


# --- Test I -------------------------------------------------------------------

def test_i_many_repeated_requests_never_exceed_the_configured_concurrency():
    registry = RunRegistry()
    executor = PipelineExecutor(max_workers=3, run_timeout_seconds=5.0)
    n = 20
    runners = [ControllableRunner() for _ in range(n)]
    runs = [registry.start_run(project_id=f"p{i}", stage="director") for i in range(n)]

    for run, runner in zip(runs, runners):
        executor.submit(run_id=run.run_id, run_registry=registry, fn=runner)

    max_observed = 0
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not all(r.completed.is_set() for r in runners):
        in_flight = sum(1 for r in runners if r.entered.is_set() and not r.completed.is_set())
        max_observed = max(max_observed, in_flight)
        for r in runners:
            if r.entered.is_set():
                r.release.set()  # idempotent - keeps draining the queue while we keep sampling
        time.sleep(0.005)

    assert all(r.completed.wait(timeout=2) for r in runners)
    assert max_observed <= 3, f"observed {max_observed} concurrently in-flight runs, exceeding max_workers=3"
    for run in runs:
        assert registry.get(run.run_id).status == RunStatus.SUCCEEDED


# --- Test F (real app, real concurrent HTTP requests) ------------------------

class _ConcurrencyTrackingDirectorController:
    """Stands in for DirectorStudioController, same minimal real-write
    behavior as conftest.py's SucceedingDirectorController, plus
    class-level concurrency bookkeeping (shared across every instance,
    since director_runner.py constructs a fresh instance per run) and a
    single shared gate so a test can hold every concurrently-running
    instance open at once before releasing them together."""

    _lock = threading.Lock()
    active = 0
    peak = 0
    hold = threading.Event()

    @classmethod
    def reset(cls):
        cls.active = 0
        cls.peak = 0
        cls.hold = threading.Event()

    def __init__(self, llm_client, project_manager):
        self.project_manager = project_manager

    def run(self, *, idea, duration, tone, audience, art_style, skip_research, scene_count_mode="default", scene_count=None):
        cls = type(self)
        with cls._lock:
            cls.active += 1
            cls.peak = max(cls.peak, cls.active)
        cls.hold.wait(timeout=10)
        with cls._lock:
            cls.active -= 1
        project = self.project_manager.create_project()
        self.project_manager.save_prompt_set(project, PromptSet())


def test_f_health_stays_responsive_while_pipeline_slots_are_saturated(monkeypatch, tmp_path):
    """Direct regression test for the exact scenario
    docs/phase1-stability-audit.md reproduced (45 concurrent POST /projects
    -> GET /health taking ~2.6s): a burst of concurrent heavy runs must not
    make GET /health slow to answer. Uses a small, explicit
    PIPELINE_MAX_CONCURRENCY so a burst of only 6 requests reliably
    saturates it - no need to reproduce the original's 45-request scale to
    prove the same mechanism is fixed."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "PIPELINE_MAX_CONCURRENCY", 2)
    _ConcurrencyTrackingDirectorController.reset()
    app = create_app()
    app.dependency_overrides[get_llm_client_factory] = lambda: FakeLLMClient
    app.dependency_overrides[get_director_controller_factory] = lambda: _ConcurrencyTrackingDirectorController
    client = TestClient(app)

    def fire_one():
        return client.post("/projects", json={"idea": "load test project"})

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fire_one) for _ in range(6)]

        assert _wait_until(lambda: _ConcurrencyTrackingDirectorController.active == 2, timeout=3.0), (
            "expected the burst to saturate PIPELINE_MAX_CONCURRENCY (2)"
        )
        # Held steady - confirms the other 4 are genuinely queued, not
        # merely not-yet-observed.
        time.sleep(0.2)
        assert _ConcurrencyTrackingDirectorController.active == 2

        health_start = time.monotonic()
        health_response = client.get("/health")
        health_elapsed = time.monotonic() - health_start

        _ConcurrencyTrackingDirectorController.hold.set()
        responses = [f.result(timeout=10) for f in futures]

    assert health_response.status_code == 200
    assert health_elapsed < 1.0, (
        f"GET /health took {health_elapsed:.3f}s while pipeline slots were saturated - "
        f"this is exactly the regression docs/phase1-stability-audit.md reproduced"
    )
    assert all(r.status_code == 202 for r in responses)
    assert _ConcurrencyTrackingDirectorController.peak == 2, (
        "PipelineExecutor allowed more than PIPELINE_MAX_CONCURRENCY runs to execute at once"
    )


# --- Test H (real app, distinct pre-existing projects) -----------------------

class _ConcurrencyTrackingProducerController:
    """Same concurrency-tracking convention as
    _ConcurrencyTrackingDirectorController, shaped for ProducerStudioController
    instead (constructed with just project_manager, .run(project_id=...))."""

    _lock = threading.Lock()
    active = 0
    peak = 0
    hold = threading.Event()

    @classmethod
    def reset(cls):
        cls.active = 0
        cls.peak = 0
        cls.hold = threading.Event()

    def __init__(self, project_manager):
        self.project_manager = project_manager

    def run(self, *, project_id):
        from shared_core.contracts.asset_manifest import ValidatedAssetManifest

        cls = type(self)
        with cls._lock:
            cls.active += 1
            cls.peak = max(cls.peak, cls.active)
        cls.hold.wait(timeout=10)
        with cls._lock:
            cls.active -= 1
        project = self.project_manager.load_project(project_id)
        manifest = ValidatedAssetManifest(is_valid=True)
        return project, manifest, None, None, None, None, None, None


def test_h_the_global_limit_cannot_be_bypassed_through_different_projects(monkeypatch, tmp_path):
    """Explicit regression test for Fix 6's Test H: PipelineExecutor has no
    per-project concept at all in its capacity accounting (only
    RunRegistry's separate one-active-run-per-project lock does, and that
    exists to stop the SAME project running twice, not to scope
    concurrency) - so many DIFFERENT projects (standing in for different
    users) submitted at once must still be capped at
    PIPELINE_MAX_CONCURRENCY in aggregate, never per-project."""
    from web_api.dependencies import get_project_manager

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "PIPELINE_MAX_CONCURRENCY", 2)
    _ConcurrencyTrackingProducerController.reset()
    app = create_app()
    app.dependency_overrides[get_producer_controller_factory] = lambda: _ConcurrencyTrackingProducerController
    client = TestClient(app)

    project_manager = get_project_manager()
    project_ids = [project_manager.create_project().project_id for _ in range(6)]

    def fire_one(project_id):
        return client.post(f"/projects/{project_id}/producer/run")

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fire_one, pid) for pid in project_ids]

        assert _wait_until(lambda: _ConcurrencyTrackingProducerController.active == 2, timeout=3.0), (
            "expected 6 distinct projects' runs to still saturate the shared PIPELINE_MAX_CONCURRENCY (2)"
        )
        time.sleep(0.2)
        assert _ConcurrencyTrackingProducerController.active == 2, (
            "the concurrency cap must be global, not per-project"
        )

        _ConcurrencyTrackingProducerController.hold.set()
        responses = [f.result(timeout=10) for f in futures]

    assert all(r.status_code == 202 for r in responses)
    assert _ConcurrencyTrackingProducerController.peak == 2

"""Phase 1.1 P0 fix (docs/phase1.1-p0-fixes.md, Fix 1/2/3/5) - a dedicated,
bounded thread pool for Director/Producer/Render/Publish pipeline execution,
deliberately SEPARATE from the anyio thread pool Starlette uses for every
sync HTTP route handler and every BackgroundTasks callable.

Why a separate pool at all (Fix 2): docs/phase1-stability-audit.md's finding
C1 showed that shared 40-slot anyio pool is what let a burst of pipeline work
starve GET /health - because BackgroundTasks.add_task(fn) (fn = one of the
run_*_pipeline functions in director_runner.py etc.) draws from the exact
same limiter as every ordinary sync route. Capping concurrency by putting a
semaphore *around* the old call site would not have fixed that: the
background-task callable itself would still occupy one of the 40 shared
slots for its entire (possibly many-minutes-long) runtime while it waited on
that semaphore. Moving execution onto this module's own executor removes
pipeline work from the shared pool entirely - the BackgroundTasks callable
that reaches this module (PipelineExecutor.submit) only ever does a fast,
non-blocking queue append and returns in microseconds, freeing its anyio
slot immediately regardless of how long the real work takes or how full
this module's own pool is.

Single-worker-deployment note (Fix 8): one PipelineExecutor instance lives
per app (app.state.pipeline_executor, created in web_api/__init__.py),
exactly one per OS process. Today's deployment (railway.json: numReplicas
1, `uvicorn api_app:app` with no --workers) runs exactly one process, so
PIPELINE_MAX_CONCURRENCY is a true, global cap. If this later moves to
multiple uvicorn workers or multiple replicas, each process gets its own
independent PipelineExecutor and its own independent budget - the
*effective* fleet-wide cap becomes PIPELINE_MAX_CONCURRENCY x process_count,
not a single cross-process limit. Making it a true cross-process limit
requires an external coordinator (e.g. a Redis-backed semaphore), which is
explicitly out of scope for this phase (no Redis/Celery/Kafka yet) - this is
a known, deliberate boundary of this fix, not an oversight.
"""
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional

from utils.logger import get_logger
from web_api.run_registry import RunRegistry

logger = get_logger("web_api.pipeline_executor")


class PipelineExecutor:
    """Bounds how many pipeline runs may actually be EXECUTING at once.
    Work beyond that bound queues inside ThreadPoolExecutor's own internal
    queue - cheap (pending callables + arguments, not OS threads or anyio
    pool slots) - and starts the moment a slot frees up. One instance per
    app; tests get their own via create_app(), the same convention
    RunRegistry already follows."""

    def __init__(self, *, max_workers: int, run_timeout_seconds: float):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.max_workers = max_workers
        self.run_timeout_seconds = run_timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pipeline-worker")
        self._lock = threading.Lock()
        self._futures: Dict[str, Future] = {}

    def submit(self, *, run_id: str, run_registry: RunRegistry, fn: Callable, **fn_kwargs) -> None:
        """Non-blocking: queues fn(run_id=run_id, run_registry=run_registry,
        **fn_kwargs) onto the bounded pool and returns immediately. fn is
        one of the existing run_*_pipeline functions (director_runner.py,
        producer_runner.py, render_runner.py, publish_runner.py) - unmodified,
        it still marks the run succeeded/failed itself exactly as before;
        this executor only adds bounded concurrency and a wall-clock
        deadline around calling it.

        Safe to call directly from a BackgroundTasks callable (itself
        running on the shared anyio pool, per this module's docstring)
        because this method never blocks - ThreadPoolExecutor.submit()
        only ever does a fast internal queue append, whether or not all
        max_workers slots are currently busy."""
        future = self._executor.submit(
            _run_with_deadline, fn, {"run_id": run_id, "run_registry": run_registry, **fn_kwargs},
            run_id, run_registry, self.run_timeout_seconds,
        )
        with self._lock:
            self._futures[run_id] = future
        future.add_done_callback(lambda _f, _run_id=run_id: self._forget(_run_id))

    def cancel(self, run_id: str, run_registry: RunRegistry) -> bool:
        """Best-effort cancellation (Fix 3/5's documented limitation):
        Python has no safe way to forcibly stop a thread that has already
        started running arbitrary code, so this can only ever cancel a run
        that is still sitting in the executor's internal queue, never one
        already executing. concurrent.futures.Future.cancel() tells us
        which case we're in: it returns True (and guarantees the callable
        will never run at all) only for a not-yet-started future - in that
        case, and only that case, this marks the run CANCELLED, since no
        concurrency slot was ever consumed by it. Returns False - and
        leaves the run's status untouched - for a run that has already
        started (or already finished): reporting CANCELLED for a run that
        may still be doing real work would be a lie this architecture
        cannot back up."""
        with self._lock:
            future = self._futures.get(run_id)
        if future is None:
            return False
        if future.cancel():
            run_registry.mark_cancelled(run_id)
            with self._lock:
                self._futures.pop(run_id, None)
            return True
        return False

    def active_count(self) -> int:
        """Diagnostic/test seam: how many submissions are currently tracked
        (running or still queued) - not part of the concurrency mechanism
        itself, only used to make the bound observable (Fix 6's tests, and
        a natural future addition to a /health or metrics endpoint)."""
        with self._lock:
            return len(self._futures)

    def _forget(self, run_id: str) -> None:
        with self._lock:
            self._futures.pop(run_id, None)

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


def _run_with_deadline(
    fn: Callable, fn_kwargs: dict, run_id: str, run_registry: RunRegistry, timeout_seconds: float
) -> None:
    """Runs fn(**fn_kwargs) on a throwaway daemon thread and waits up to
    timeout_seconds for it to finish, all from within one PipelineExecutor
    worker thread.

    This is what actually enforces Fix 3's wall-clock timeout, and it is
    intentionally honest about what it can and cannot guarantee (Fix 5):

    - On success or a handled failure (fn itself already calls
      run_registry.mark_succeeded/mark_failed - this wrapper never touches
      that path), the daemon thread finishes within the deadline, this
      function returns, and the PipelineExecutor worker slot is freed
      immediately.
    - On timeout: this function marks the run TIMED_OUT and returns -
      freeing the PipelineExecutor worker slot (Fix 3/5's "concurrency
      slot released on timeout" requirement) - but the daemon thread
      itself is NOT forcibly stopped, because Python provides no safe API
      to do that. It keeps running in the background until whatever
      bounded, per-call timeout already exists at the LLM-client or
      ffmpeg-subprocess layer eventually unwinds it. Any outcome it
      reports after that point is silently discarded: RunRegistry._finish
      is a no-op once a run is already terminal, so a late mark_succeeded/
      mark_failed can never overwrite the TIMED_OUT verdict already
      recorded and already visible to the API/frontend.

    This means PIPELINE_MAX_CONCURRENCY slots can, in the worst case
    (every slot occupied by a stage that ignores its own timeout budget),
    temporarily correspond to PIPELINE_MAX_CONCURRENCY *plus* that many
    abandoned daemon threads still finishing in the background - a bounded,
    documented, and vastly smaller number than the unbounded-concurrency
    failure mode this fix replaces, not a claim of perfect cleanup.
    """
    done = threading.Event()

    def _target():
        try:
            fn(**fn_kwargs)
        except Exception as exc:
            # Defensive only: all four existing run_*_pipeline functions
            # already catch everything themselves and call mark_failed
            # before returning. This exists so a future runner that forgot
            # to do the same still ends in a recorded, terminal state
            # instead of silently vanishing.
            logger.exception(f"Pipeline run {run_id} raised uncaught from its runner function")
            run_registry.mark_failed(run_id, error=str(exc))
        finally:
            done.set()

    worker = threading.Thread(target=_target, name=f"pipeline-run-{run_id}", daemon=True)
    worker.start()
    finished_in_time = done.wait(timeout=timeout_seconds)

    if not finished_in_time:
        logger.warning(
            f"Pipeline run {run_id} exceeded its {timeout_seconds:g}s wall-clock timeout - "
            f"marking TIMED_OUT and releasing its concurrency slot; the underlying thread may "
            f"still be running in the background (see PipelineExecutor docstring)"
        )
        run_registry.mark_timed_out(run_id, timeout_seconds=timeout_seconds)

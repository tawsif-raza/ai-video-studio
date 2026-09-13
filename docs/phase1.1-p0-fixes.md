# AI Video Studio — Phase 1.1 P0 Crash Fixes

**Scope:** implements the three fixes scoped by `docs/phase1-stability-audit.md`'s findings C1 (shared thread-pool exhaustion), C2 (unbounded run duration), and C3 (in-memory RunRegistry / orphaned render artifacts). No Phase 2 work (distributed queue, database, billing, auth, autoscaling) is included, per this phase's own rules.

---

## Fix 1 — Global Pipeline Concurrency Limit

**Problem:** Director/Producer/Render/Publish execution had no concurrency ceiling. Every run was dispatched via `BackgroundTasks.add_task(run_*_pipeline, ...)`, which Starlette runs through `run_in_threadpool` — the *same* process-wide, 40-slot `anyio` thread pool used by every sync HTTP route (including the health check).

**Root Cause:** `web_api/{director,producer,render,publish}_runner.py` functions ran directly inside a `BackgroundTasks` callable with no bound on how many could execute at once, and no isolation from the pool ordinary API traffic depends on.

**Implementation:** A new module, `web_api/pipeline_executor.py`, adds `PipelineExecutor` — a dedicated `concurrent.futures.ThreadPoolExecutor` sized by `PIPELINE_MAX_CONCURRENCY` (default **4**), held on `app.state.pipeline_executor` (one per app instance, same convention as `RunRegistry`). Every router now calls `background_tasks.add_task(pipeline_executor.submit, run_id=..., run_registry=..., fn=run_director_pipeline, ...)` instead of calling the runner directly. `PipelineExecutor.submit()` never blocks — it only does a fast internal queue append — so the anyio-pool slot the `BackgroundTasks` dispatch itself occupies is freed in microseconds regardless of how long the real pipeline work takes or how full `PipelineExecutor`'s own pool is. Concurrency beyond the cap queues inside `ThreadPoolExecutor`'s own internal queue (cheap: pending callables + args, not OS threads or anyio slots).

**Why 4, not 40:** deliberately *not* tied to or derived from anyio's 40-slot default (explicitly prohibited by this phase's rules). Sized for today's actual deployment: `railway.json` (`numReplicas: 1`, `uvicorn api_app:app` with no `--workers`) runs exactly one OS process; every pipeline slot is CPU/LLM/ffmpeg-bound work sharing that one process with the API itself. A small cap leaves the process real headroom to keep answering ordinary requests — and the health check — even while every pipeline slot is busy. Configurable via `PIPELINE_MAX_CONCURRENCY` env var.

**Files Changed:** `web_api/pipeline_executor.py` (new), `web_api/dependencies.py` (+`get_pipeline_executor`), `web_api/__init__.py` (+`app.state.pipeline_executor`), `web_api/routers/{projects,producer,render,publish}.py` (swapped runner target), `config.py` (+`PIPELINE_MAX_CONCURRENCY`).

**Tests Added:** `tests/web_api/test_pipeline_executor.py::test_a_single_pipeline_run_succeeds`, `::test_b_excess_runs_queue_behind_the_configured_maximum`, `::test_i_many_repeated_requests_never_exceed_the_configured_concurrency`.

**Before Measurement:** unbounded — any number of concurrent runs could be in flight at once (`docs/phase1-stability-audit.md` finding C1).

**After Measurement:** `test_b` proves exactly `max_workers` (2 of 5 submitted) execute concurrently, holding steady for 300ms before the rest are released; `test_i` submits 20 runs against `max_workers=3` and confirms concurrently-in-flight count never exceeds 3 across the full drain.

**Verification method:** `pytest tests/web_api/test_pipeline_executor.py -v` (10/10 pass).

**Remaining Risk:** Fix 8 documents the single-process boundary of this cap explicitly — it is not yet a cross-process/cross-replica limit.

---

## Fix 2 — Keep Ordinary HTTP Traffic Responsive

**Problem:** Confirm that after Fix 1, heavy pipeline runs can no longer monopolize the shared pool `/health`, project listing, and project status depend on.

**Root Cause:** Same as Fix 1 — the shared anyio pool was the single point of contention. A semaphore placed *around* the old direct call site would not have fixed this: the `BackgroundTasks` callable itself would still have occupied a shared-pool slot for its entire runtime while waiting on that semaphore. The real fix had to *move the execution itself* off that pool, not just gate entry to it.

**Implementation:** No special-cased `/health` route was added — that would have hidden the problem rather than fixed it, and the phase's rules explicitly forbid it. `GET /health` (`web_api/routers/system.py`) is unchanged, still a plain sync `def`, still dispatched through the shared anyio pool exactly as before. It now works under load purely because Fix 1 removed pipeline work from that pool entirely, so the pool stays uncontended for ordinary traffic regardless of pipeline load.

**Files Changed:** none beyond Fix 1 (this fix is a verification of Fix 1's effect, not new code).

**Tests Added:** `tests/web_api/test_pipeline_executor.py::test_f_health_stays_responsive_while_pipeline_slots_are_saturated` — saturates `PIPELINE_MAX_CONCURRENCY=2` with a 6-request burst through the real app (`create_app()` + real concurrent HTTP requests via a thread pool) and asserts `GET /health` answers in under 1 second while every pipeline slot is busy.

**Before Measurement (original audit reproduction):** 45 concurrent `POST /projects` → `GET /health` took **~2.60s**.

**After Measurement (this session, re-run against the fixed app — see Fix 7 for full detail):** 45 concurrent `POST /projects` → `GET /health` took **0.001s**. Also confirmed at 5, 10, and 20 concurrent heavy runs (0.001–0.002s in every case).

**Verification method:** `pytest tests/web_api/test_pipeline_executor.py::test_f_health_stays_responsive_while_pipeline_slots_are_saturated -v`, plus the standalone reproduction script described in Fix 7.

**Remaining Risk:** every *other* sync route (auth, project listing, media upload) still shares the anyio pool with each other — this is fine, since none of them do multi-minute work, but a future endpoint that does slow synchronous work outside the pipeline path would reintroduce a version of this problem. Not observed in this codebase today.

---

## Fix 3 — Per-Run Wall-Clock Timeout

**Problem:** No pipeline run had an overall timeout. A single legitimate request (e.g. `scene_count=100`, the configured maximum) could occupy a concurrency slot for tens of minutes; a genuinely stuck stage could occupy one forever.

**Root Cause:** Each individual LLM call already had its own 60s timeout (`llm/gemini_client.py`, `llm/gpt_client.py`) and ffmpeg its own subprocess-level timeout (`RenderOptions.timeout_seconds`, default 120s, enforced by `subprocess.run(timeout=...)`, which really does kill the process) — but nothing bounded the *whole pipeline run's* wall-clock duration.

**Three distinct concepts, not to be confused:**
- **Request timeout** — the frontend's 60s `AbortController` (`frontend/api/client.ts`), bounding how long a *browser* waits for one HTTP response. Irrelevant here since these are `202 Accepted` responses returned in milliseconds.
- **External provider timeout** — the LLM client's 60s-per-call timeout, or ffmpeg's subprocess timeout. Bounds one call, not the whole run.
- **Pipeline timeout (new, this fix)** — a wall-clock ceiling on the *entire* Director/Producer/Render/Publish run, independent of and in addition to the above.

**Implementation:** `PipelineExecutor._run_with_deadline` runs the actual runner function (`fn`) on a throwaway `daemon=True` thread and waits up to `PIPELINE_TIMEOUT_SECONDS` (default **1800s / 30 minutes**) via `threading.Event.wait(timeout=...)`. If the deadline passes first, it calls `run_registry.mark_timed_out(run_id, timeout_seconds=...)` and returns — freeing the `PipelineExecutor` slot immediately — **without** attempting to forcibly stop the daemon thread, because Python provides no safe API to do that.

**Why 1800s:** sized against the audit's own worst-case estimate for a legitimate `MAX_SCENE_COUNT=100` Director run (~100–200 sequential per-shot LLM calls, ~30–35 minutes in the happy path) — a backstop against a genuinely stuck run, not a tool for capping normal heavy usage (Fix 1's concurrency cap is what actually protects the API under load, per this phase's own rule 11). Configurable via `PIPELINE_TIMEOUT_SECONDS`; raise it (or lower `MAX_SCENE_COUNT`) if real measurements show typical heavy runs exceeding it.

**Files Changed:** `web_api/pipeline_executor.py` (`_run_with_deadline`), `config.py` (+`PIPELINE_TIMEOUT_SECONDS`).

**Tests Added:** `tests/web_api/test_pipeline_executor.py::test_e_a_timed_out_run_releases_its_concurrency_slot_and_late_results_are_discarded`, `::test_g_a_stuck_heavy_run_cannot_block_the_queue_forever`.

**Before Measurement:** unbounded — a stuck run occupied its slot forever.

**After Measurement:** with `run_timeout_seconds=0.2` (test-scale), a stuck run reliably transitions to `TIMED_OUT` within the deadline and its slot is immediately available to the next queued run (`test_e`); three runs queued behind a permanently-stuck one all complete rather than starving forever (`test_g`).

**Verification method:** `pytest tests/web_api/test_pipeline_executor.py -k "test_e or test_g" -v`.

**Remaining Risk (stated plainly, not hidden):** the abandoned daemon thread is **not** forcibly stopped. It keeps running in the background until whatever bounded per-call timeout already exists at the LLM-client or ffmpeg-subprocess layer eventually unwinds it. In the worst case, every one of `PIPELINE_MAX_CONCURRENCY` slots could correspond to an abandoned thread still finishing in the background — a bounded, small, documented number, not the unbounded-concurrency failure mode this phase replaces. See Fix 5 for the full accounting of what is and isn't guaranteed here.

---

## Fix 4 — Run State Reflects Timeout/Failure

**Problem:** The frontend must never be left polling a `RUNNING` status indefinitely after a timeout.

**Root Cause:** `RunStatus` (`web_api/run_registry.py`) had no state for "exceeded its time budget" — the closest existing signal, `FAILED`, would have conflated a real pipeline failure with an operational timeout, losing the distinction FIX 4 explicitly asks for.

**Implementation:** Added `RunStatus.TIMED_OUT` and `RunStatus.CANCELLED` (the latter for Fix 5's cancellation path). Both are included in a new shared `TERMINAL_STATUSES` frozenset (`web_api/run_registry.py`), which `web_api/sse.py`'s stream-closing check and both `_to_status_response` functions (`web_api/routers/render.py`, `web_api/routers/publish.py`) now use — an SSE subscriber sees a `timed_out`/`cancelled` event and the stream closes, exactly like `completed`/`failed` already did; `GET .../render/status` and `GET .../publish/status` report `current_stage: "timed_out"` / `"cancelled"` with `progress: 100`, never leaving a client to infer state from silence.

Recorded on a `TIMED_OUT`/`CANCELLED` `Run`: `run_id`, `project_id`, `stage` (all pre-existing `Run` fields, untouched), `finished_at` (timestamp), and `error` — a human-readable, internal-detail-free string (`"Pipeline run exceeded its 1800s wall-clock timeout"` / `"Run was cancelled before it started executing"`) with no stack trace or exception internals ever exposed. Elapsed time is derivable as `finished_at - started_at` rather than stored redundantly.

**Files Changed:** `web_api/run_registry.py` (new statuses, `TERMINAL_STATUSES`, `mark_timed_out`, `mark_cancelled`, idempotency guard in `_finish`/`mark_running`), `web_api/sse.py` (`_STAGE_LABELS`, `_events_for`, terminal-status import), `web_api/routers/render.py` and `web_api/routers/publish.py` (`_to_status_response`).

**Tests Added:** `tests/web_api/test_run_registry.py::test_mark_timed_out_sets_terminal_state_and_error`, `::test_mark_cancelled_sets_terminal_state_and_error`, `::test_timed_out_run_releases_project_lock_for_a_new_run`.

**Before Measurement:** N/A — no such state existed.

**After Measurement:** `test_mark_timed_out_sets_terminal_state_and_error` confirms the transition, the recorded error text, and that `RunStatus.TIMED_OUT` is a member of `TERMINAL_STATUSES`.

**Verification method:** `pytest tests/web_api/test_run_registry.py -v`.

**Remaining Risk:** none identified for this fix specifically.

---

## Fix 5 — Resource Cleanup

**Problem:** Timeout/failure/cancellation must release the concurrency slot, and this phase's rules explicitly forbid claiming subprocess-level cancellation the implementation cannot back up.

**What is genuinely guaranteed:**
- **Concurrency slot:** always released, on every path (success, failure, timeout, cancellation) — proven directly by `test_c` (failure), `test_d` (cancellation), `test_e` (timeout), and `test_i` (bulk, mixed drain).
- **A late result can never corrupt an already-recorded verdict:** `RunRegistry._finish`'s idempotency guard (Fix 4) means a stray `mark_succeeded`/`mark_failed` call from an abandoned thread, arriving after `TIMED_OUT` was already recorded, is silently discarded — proven directly by `test_a_late_success_after_timeout_is_discarded_not_overwriting_timed_out` and its failure-path counterpart.
- **A queued-but-not-yet-started run can be cancelled with a hard guarantee it will never run at all** — `concurrent.futures.Future.cancel()` returning `True` is a real, load-bearing guarantee from the standard library, not a best-effort guess. Proven by `test_d_cancelling_a_queued_run_prevents_it_from_ever_starting`.
- **ffmpeg subprocesses:** unaffected by this phase — `execution_engine/ffmpeg_executor.py`'s existing atomic temp-file-then-rename behavior and its own `subprocess.run(timeout=...)` (a real, OS-level process kill) were not modified and continue to work exactly as before.

**What is explicitly NOT guaranteed, documented rather than hidden:**
- **A run already executing cannot be forcibly stopped.** Python has no safe API to kill a running thread. `PipelineExecutor.cancel()` returns `False` for an already-running run and leaves its status untouched (`test_d_cancelling_an_already_running_run_is_a_documented_no_op`) — reporting `CANCELLED` for a run that might still be doing real work would be a lie this architecture cannot back up.
- **A timed-out run's underlying thread is not stopped either** — it keeps running until the LLM-client or ffmpeg-subprocess layer's own existing timeout unwinds it (see Fix 3's Remaining Risk). Open file handles, network connections, or an in-flight ffmpeg subprocess belonging to that abandoned thread are cleaned up only by whatever cleanup the *existing*, unmodified stage code already does on its own exit path — this phase adds no new cleanup hook for that case, because doing so safely would require restructuring Director/Producer's controllers to be cooperatively cancellable, which is explicitly out of scope ("do not redesign the entire pipeline").

**Files Changed:** none beyond Fix 1/3 (this fix is the documented behavior of `PipelineExecutor`, not separate code).

**Tests Added:** covered by Fix 1/3's tests above (`test_c`, `test_d` x2, `test_e`) plus `tests/web_api/test_run_registry.py`'s two late-result tests.

**Verification method:** `pytest tests/web_api/test_pipeline_executor.py tests/web_api/test_run_registry.py -v`.

**Remaining Risk:** stated above — this is a documented architectural limitation of a synchronous, thread-based pipeline, not a defect introduced by this phase. Closing it fully would require Director/Producer/Render/Publish controllers to accept and periodically check a cancellation token, which is a real design change appropriately scoped to a later phase.

---

## Fix 6 — Regression Tests

All nine required tests (A–I) were implemented, all passing:

| Test | File | Proves |
|---|---|---|
| A | `test_pipeline_executor.py::test_a_single_pipeline_run_succeeds` | One run runs and succeeds. |
| B | `::test_b_excess_runs_queue_behind_the_configured_maximum` | Exactly `max_workers` execute concurrently; the rest queue. |
| C | `::test_c_a_failed_run_releases_its_concurrency_slot` | A failure frees the slot for the next run. |
| D | `::test_d_cancelling_a_queued_run_prevents_it_from_ever_starting`, `::test_d_cancelling_an_already_running_run_is_a_documented_no_op` | Cancellation frees a not-yet-started slot with a hard guarantee; an already-running one is honestly left alone. |
| E | `::test_e_a_timed_out_run_releases_its_concurrency_slot_and_late_results_are_discarded` | A timeout frees the slot; a late result can't corrupt the recorded verdict. |
| F | `::test_f_health_stays_responsive_while_pipeline_slots_are_saturated` | `GET /health` stays fast (<1s) while every pipeline slot is saturated, through the real app over real HTTP. |
| G | `::test_g_a_stuck_heavy_run_cannot_block_the_queue_forever` | A permanently-stuck run cannot starve everything queued behind it. |
| H | `::test_h_the_global_limit_cannot_be_bypassed_through_different_projects` | The cap is global across distinct projects/users, not per-project — proven through the real Producer router with 6 distinct pre-existing projects. |
| I | `::test_i_many_repeated_requests_never_exceed_the_configured_concurrency` | 20 repeated requests against `max_workers=3` never exceed 3 concurrently in flight. |

Plus supporting tests: `test_run_registry.py` (+6 tests for the new statuses and idempotency guard) and `test_reap_orphaned_render_artifacts.py` (+7 tests for Fix 9).

**No existing test was weakened or deleted.** 16 existing tests across `test_runs.py`, `test_producer.py`, `test_render.py`, `test_publish.py`, `test_events_router.py`, and the four `tests/integration/test_api_*_pipeline.py` files were updated to poll for a run's terminal status (via a new `wait_for_run` helper in `tests/web_api/conftest.py`) instead of asserting immediately after `POST .../run` returns — a required, honest adaptation, not a weakening: before this phase, `TestClient` genuinely did run background tasks to completion synchronously within the request cycle (Starlette awaits `BackgroundTasks` before considering a response finished); after Fix 1, real pipeline execution happens on `PipelineExecutor`'s own decoupled thread pool, so that guarantee no longer holds. Every updated assertion still checks exactly the same outcome it did before — only the synchronization mechanism changed.

**Verification method:** `pytest tests/web_api/test_pipeline_executor.py tests/web_api/test_run_registry.py tests/project_manager/test_reap_orphaned_render_artifacts.py -v` (39/39 pass); full suite below.

---

## Fix 7 — Reproduce the Original Failure

Re-ran the exact original reproduction from `docs/phase1-stability-audit.md` against the fixed app (fake `DirectorStudioController` that blocks for 3s per run — no real LLM/ffmpeg calls, safe and free — dispatched through the real `web_api.create_app()`, `PipelineExecutor` wired with the new default `PIPELINE_MAX_CONCURRENCY=4`), and escalated to 5/10/20 concurrent heavy runs as requested. All numbers below are from actual runs in this session, not estimated.

| Concurrency | Accepted (202) | GET /health latency | Max individual POST latency | Errors |
|---|---|---|---|---|
| 45 (original scale) | 45/45 | **0.001s** | 0.137s | 0 |
| 5 | 5/5 | 0.002s | 0.050s | 0 |
| 10 | 10/10 | 0.001s | 0.084s | 0 |
| 20 | 20/20 | 0.001s | 0.097s | 0 |

**Before (original audit):** 45 concurrent `POST /projects` → `GET /health` ≈ **2.60s**.
**After (this session):** 45 concurrent `POST /projects` → `GET /health` ≈ **0.001s** — a ~2,600x improvement, and the same near-zero result held at every tested concurrency level.

Note on "active pipeline runs" reported by `PipelineExecutor.active_count()` during these runs: it reported the full submitted count (45/5/10/20) at burst peak. This is correct and expected — `active_count()` tracks everything currently *tracked* (running **or** queued), not just concurrently-*executing* work; the actual concurrent-execution cap (4, proven separately by the unit-level `test_b`/`test_i`) is enforced inside `PipelineExecutor`'s internal `ThreadPoolExecutor`, which is exactly why all 45 requests could still be *accepted* instantly while genuine execution stayed bounded.

CPU/RAM: `resource.getrusage` is POSIX-only and unavailable on this Windows development machine (the same limitation `execution_engine/ffmpeg_executor.py` already documents and degrades gracefully for) — **not measured**, consistent with this phase's rule against fabricating numbers. Should be captured in a Linux/container environment (matching the actual Nixpacks/Railway deployment) before this is considered fully verified end-to-end.

**Verification method:** the reproduction script used for this table is preserved in this session's scratchpad; the same measurement is also exercised as an automated, permanent regression test in `test_f_health_stays_responsive_while_pipeline_slots_are_saturated`.

---

## Fix 8 — Single-Worker Safety

**What `PipelineExecutor` protects today:** with the current deployment (`railway.json`: `numReplicas: 1`; `uvicorn api_app:app` with no `--workers` flag) there is exactly one OS process, and `app.state.pipeline_executor` is one instance per process — so `PIPELINE_MAX_CONCURRENCY` is a true, global, exact cap on how many pipeline runs may execute at once, anywhere in this deployment.

**What happens if multiple API workers or replicas are introduced later:** each process gets its **own independent** `PipelineExecutor` instance with its **own independent** budget. The limiter is per-process, not global across processes. If Railway's `numReplicas` were raised, or `uvicorn --workers N` were added, the *effective* fleet-wide concurrency ceiling becomes `PIPELINE_MAX_CONCURRENCY x process_count` — e.g. 3 replicas at the default of 4 would allow up to 12 pipeline runs executing simultaneously across the fleet, not 4. This is very likely still an improvement over today's unbounded-per-process behavior, but it is **not** what "a global limit of 4" would suggest to someone reading the config value alone.

**Why this isn't fixed now:** a true cross-process/cross-replica limit requires an external, shared coordinator (e.g. a Redis-backed semaphore or a real job queue with a global worker pool) — explicitly out of scope for this phase (rule: no Redis/Celery/Kafka yet). `PLAN.md`'s own `JOB-01`/`SCALE-01` tasks already anticipate exactly this follow-up work.

**Files Changed:** none (documentation of existing, already-implemented behavior).

**Verification method:** code inspection of `web_api/pipeline_executor.py`'s docstring and `create_app()`'s per-instance construction; no multi-process test was run (would require actually running multiple worker processes, which is Phase 2-shaped infrastructure work).

**Remaining Risk:** if `railway.json`'s `numReplicas` or a `--workers` flag changes before a real cross-process coordinator exists, `PIPELINE_MAX_CONCURRENCY`'s effective meaning silently changes from "global cap" to "per-process cap" — flagged here explicitly so that decision is never made silently.

---

## Fix 9 — P1 RunRegistry Remediation

**Investigation (as required, before implementing anything):**
- **What state is lost on restart:** every `Run` object in `RunRegistry` — the entire in-memory dict of run bookkeeping (`_runs`, `_active_by_project`, `_latest_by_project_stage`). This was already true before this phase and is explicitly by design (`run_registry.py`'s own pre-existing docstring: *"an API process restart loses live run state, never outcome state"*).
- **What files become orphaned:** exactly two shapes, both from `execution_engine/ffmpeg_executor.py`: a `*.part.<ext>` temp output (renamed to its final name only on a verified successful render — one still present under this name was never a finished render) and a `*.stderr.log` (deleted by `execute()` on every code path it itself completes — one still present was orphaned by something that killed the process before `execute()` could reach its own cleanup, e.g. exactly the Fix-1-addressed crash mode).
- **Whether runs can be reconstructed from existing project state:** no, not meaningfully. `ProjectState` (`project_manager/project.py`) has no "render in progress" state distinct from `EDIT_PLAN_READY` — a project whose render was interrupted mid-flight is left at `EDIT_PLAN_READY`, indistinguishable from one that simply hasn't been rendered yet. Reconstructing "a run was in flight" would require adding new persistent state this phase's rules explicitly forbid inventing ("do not invent persistence architecture before Phase 2").
- **Whether startup cleanup is currently possible:** yes, for the two orphaned-file shapes above — they are unambiguous to identify without any `Run`/`RunRegistry` history at all, purely from their filename pattern and the guarantee that `ffmpeg_executor.py` only ever produces them in those two specific, well-defined circumstances.

**Implementation (smallest safe remediation, as required):**
1. `ProjectManager.reap_orphaned_render_artifacts()` (`project_manager/manager.py`) scans every project's `renders/` directory and removes `*.part.*` and `*.stderr.log` files. Never touches a finished render (`video.mp4`, no such suffix) or any report file.
2. Wired into a new FastAPI `lifespan` context manager in `web_api/__init__.py`, run once at app startup, before the app accepts requests. Logs what was removed.
3. **Documented, not solved:** the limitation above (a project whose render was interrupted is simply left at `EDIT_PLAN_READY`, discoverable only by the user noticing it never advanced and re-running it) is recorded directly in `reap_orphaned_render_artifacts`'s own docstring rather than worked around with new invented state.

**Files Changed:** `project_manager/manager.py` (+`reap_orphaned_render_artifacts`), `web_api/__init__.py` (+`_lifespan`).

**Tests Added:** `tests/project_manager/test_reap_orphaned_render_artifacts.py` (7 tests: removes each orphaned shape, never touches a finished render, safe with no projects/no renders dir, covers multiple projects independently, and one end-to-end test proving the reaper is actually wired into the real app's startup lifespan via `with TestClient(app) as client`).

**Before Measurement:** orphaned `.part.*`/`.stderr.log` files persisted on disk forever after a hard kill.

**After Measurement:** `test_web_api_startup_lifespan_runs_the_reaper` proves a file planted before app startup is gone immediately after startup completes.

**Verification method:** `pytest tests/project_manager/test_reap_orphaned_render_artifacts.py -v`.

**Remaining Risk:** the "project stuck at EDIT_PLAN_READY with no explanation" limitation above is real and user-visible; surfacing it properly (e.g. a "render was interrupted, please retry" signal) needs new persistent state and is correctly deferred to Phase 2, per this phase's own rules.

---

## Verification Summary

1. **Full existing test suite:** `pytest` — **811 passed, 25 skipped** (0 failed). The 25 skips are the same pre-existing, environment-only skips as before this phase (24 for no local `ffmpeg` binary, 1 for no live YouTube credentials) — nothing new skipped, nothing weakened.
2. **All new regression tests:** 39 new/updated-assertion tests across `test_pipeline_executor.py` (10), `test_run_registry.py` (+6), `test_reap_orphaned_render_artifacts.py` (7), plus 16 existing tests adapted to the new async execution model (`wait_for_run`) — all passing.
3. **Original thread-pool starvation reproduction, re-run:** see Fix 7 — `/health` latency dropped from ~2.60s to ~0.001s at the original 45-concurrent scale, and stayed at ~0.001–0.002s at 5, 10, and 20 concurrent heavy runs.
4. **Heavy concurrent generation:** re-run at 5/10/20/45 concurrency (Fix 7); all requests accepted, zero errors, execution genuinely bounded (proven at the unit level by `test_b`/`test_i`/`test_f`/`test_h`).
5. **Timeout behavior:** `test_e`, `test_g` — a stuck run times out on schedule and never starves runs queued behind it.
6. **Failure/cancellation behavior:** `test_c`, `test_d` (x2) — both release the concurrency slot correctly; an already-running run's cancellation limitation is honestly represented, not glossed over.
7. **Health responsiveness:** confirmed both as a live reproduction (Fix 7) and as a permanent automated regression test (`test_f`).
8. **CPU/RAM:** not measured — no POSIX `resource` module on this Windows development machine. Explicitly flagged as unverified rather than estimated; should be captured against a Linux/container environment matching the real Nixpacks/Railway deployment.

---

## Final Report

```text
Total tests passed: 811
Total tests failed: 0
(25 skipped - pre-existing, environment-only: 24 no local ffmpeg, 1 no live YouTube creds)

Original reproduction:
Before: 45 concurrent POST /projects -> GET /health ~= 2.60s
After:  45 concurrent POST /projects -> GET /health ~= 0.001s
        (also confirmed at 5, 10, and 20 concurrent heavy runs: 0.001-0.002s in every case)

Maximum pipeline concurrency: PIPELINE_MAX_CONCURRENCY = 4 (configurable; per-process - see Fix 8)
Pipeline timeout: PIPELINE_TIMEOUT_SECONDS = 1800s / 30 minutes (configurable)

Health latency under heavy load:
Before: ~2.60s (45 concurrent heavy runs)
After:  ~0.001s (same scenario, and at 5/10/20 concurrency)

Remaining P0: none identified for the shared-thread-pool-exhaustion mechanism this phase targeted.
Remaining P1: cross-process/cross-replica concurrency coordination (Fix 8) if numReplicas/--workers
              changes before a real external coordinator exists; CPU/RAM under real load unmeasured
              on this platform (Fix 7).
Remaining P2: an interrupted render leaves its project silently stuck at EDIT_PLAN_READY with no
              "this was interrupted, please retry" signal (Fix 9); a timed-out run's abandoned
              background thread is not forcibly stopped (Fix 3/5, architecturally unavoidable
              without cooperative-cancellation support in Director/Producer/Render/Publish
              controllers - correctly out of scope for this phase).
```

STOP — Phase 1.1 P0 fixes and verification complete. No Phase 2 work (distributed architecture, streaming, billing, authentication, traffic optimization, database redesign, autoscaling) was started.

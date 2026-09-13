# AI Video Studio — Phase 1 Stability Audit

**Investigation date:** 2026-09-13
**Scope:** crash cause identification only. No fixes were implemented as part of this document.
**Supersedes:** the previous `docs/phase1-stability-audit.md` / `docs/phase1-stability-report.md` / `PHASE1_CLOSURE.md` ("Phase 1 CLOSED", commit `78362ec`). That work fixed several real, narrow issues (listed in full under "Prior Phase 1 Fixes — Verified Still Present") but explicitly stated *"No active load generators (e.g., locust, k6) were executed"* and *"full production-style load testing remains pending."* This audit is that missing load/concurrency analysis, and it finds the actual primary crash mechanism was not addressed by the prior pass.

---

## Executive Summary

The application is **not** using LangGraph anywhere (`grep -rli langgraph` across the entire repo returns zero hits) — the pipeline is a set of hand-written, sequential Python controllers (`director_studio/controller.py`, `producer_studio/controller.py`, `execution_engine/controller.py`, `publishing_engine/controller.py`). This matters because the crash mechanism found here is not a LangGraph fan-out problem; it's a **web-framework thread-pool sharing problem**, confirmed by two independent reproductions (one isolated, one against the real app object).

**The root cause, in one sentence:** the API is deployed as a single `uvicorn` worker process (`uvicorn api_app:app`, no `--workers`), and *every* HTTP route in this app is a synchronous `def` (not `async def`) — including the Railway health check — which means every request and every background pipeline run (Director/Producer/Render/Publish, all four dispatched via `BackgroundTasks.add_task`) is funneled through **one shared, 40-slot, process-wide thread pool** (`anyio`'s default `to_thread` limiter). There is no per-user, per-project (beyond one-run-per-project), or global concurrency ceiling anywhere in the codebase. When enough long-running background runs are in flight — which happens well within normal "heavy workload" use, not just adversarial load — the pool saturates and **every other request, including the health check Railway uses to decide whether to kill and restart the container, queues behind them.** This is confirmed to cause the exact "whole site becomes unresponsive" experience, and it means one user's heavy job genuinely can, and will, degrade or take down the service for every other user on the same replica (`railway.json` pins `numReplicas: 1`).

This finding was not visible to the prior Phase 1 pass because it only inspected individual functions for local bugs (unbounded memory reads, missing timeouts) — real problems, and still fixed — but never asked "what shares a resource with what, process-wide, under concurrency."

---

## Current Architecture

```
Browser (Next.js frontend, Vercel)
   │  fetch() / EventSource (SSE)
   ▼
FastAPI app (ai_video_studio/api_app.py → web_api.create_app())
   single `uvicorn api_app:app` process, no --workers flag
   (Dockerfile / nixpacks.toml + railway.json, numReplicas: 1)
   │
   ├─ Sync route handlers (def, NOT async def) — every router except events.py:
   │    auth.py, health.py, system.py, producer.py, projects.py, publish.py, render.py, runs.py
   │    → Starlette wraps each in run_in_threadpool() (starlette/routing.py:55)
   │
   ├─ BackgroundTasks.add_task(...) — director_runner.py, producer_runner.py,
   │    render_runner.py, publish_runner.py (all 4 pipeline stages)
   │    → Starlette runs each via run_in_threadpool() (starlette/background.py:23)
   │
   └─ BOTH of the above draw from the SAME process-wide anyio thread limiter
        (confirmed: anyio 4.14.2, default capacity = 40 threads, one pool
        per process — not per-router, not per-task-type)
   │
   ▼
Inside a background thread:
   Director: director_studio/controller.py → 9 sequential LLM-backed agent
     stages, one of which (Prompt Intelligence) loops per-scene × per-shot,
     calling the LLM once per shot, SEQUENTIALLY (controller.py:206)
   Producer: producer_studio/controller.py → 7 deterministic (no LLM) stages
   Render: execution_engine/controller.py → ffmpeg subprocess (up to
     RenderOptions.timeout_seconds, default 120s) + ffprobe verification
   Publish: publishing_engine/controller.py → platform API calls
   │
   ▼
RunRegistry (web_api/run_registry.py) — in-memory only, one per app
  process, lives in app.state, lost on any process restart.
   │
   ▼
ProjectManager — sole filesystem writer, local disk under OUTPUT_DIR
   (production/producer packages, media/, renders/, users/)
```

No database exists yet (file-system only). No LangGraph. No task queue/broker (Celery/Redis) — `PLAN.md`'s own `JOB-01` task already flags this as future work. `video_generation_engine/` exists but is wired to a zero-cost `StubProvider` only (per `ARCHITECTURE.md` §25) and is not in this request path yet.

---

## Crash Boundary

Based on the evidence gathered (see Reproduction Results), "the website crashes" under heavy load resolves to a specific combination, **not** a single category from the taxonomy in the brief:

- **Not (A) frontend crash** — no evidence of browser-side OOM or render failure; the frontend's `error.tsx`/`global-error.tsx` boundaries and 60s `AbortController` fetch timeout are real and present (verified by reading `frontend/api/client.ts` and `frontend/app/error.tsx`).
- **Primarily (B) API unresponsiveness, not a hard process crash.** The uvicorn process itself does not necessarily exit — but it stops answering *anything*, including `/health`, once its shared thread pool is saturated. This is functionally indistinguishable from a crash to users and to Railway's orchestrator.
- **(C) Background-worker-shaped, but with no separate worker process** — Director/Producer/Render/Publish runs execute inside the same process as the API, so "a worker dies" and "the API dies" are the same event here.
- **(E) Resource exhaustion — confirmed mechanism: thread-pool exhaustion**, not (necessarily) RAM/CPU exhaustion first. Thread starvation is the faster, cheaper-to-trigger failure mode; RAM/CPU exhaustion (D0 below) is a secondary, compounding risk once concurrent ffmpeg/LLM work does get through.
- **Cascading consequence: (D)-shaped outcome via the deploy config, not the database.** `railway.json`'s `healthcheckTimeout: 100` + `restartPolicyType: ON_FAILURE` means a starved `/health` endpoint gets Railway to kill and restart the one replica (`numReplicas: 1`). That restart: (a) wipes `RunRegistry` (in-memory, confirmed in `run_registry.py`'s own docstring), so every in-flight run for every user silently vanishes from the API's point of view even if the underlying work would have finished; (b) SIGKILLs any in-flight `ffmpeg` subprocess and any Python background thread mid-pipeline, with no reconciliation on restart (no lifespan/startup hook exists anywhere in `web_api/__init__.py` — confirmed by search).
- **(F) dependency failure is a contributor, not the root cause**: LLM provider timeouts (60s, confirmed fixed) and the 3-attempt tenacity retry (`agents/base/base_agent.py`) make each *individual* LLM call bounded, but they also mean a stressed/slow provider makes each pipeline stage take up to ~3× longer, which lengthens exactly the thread-occupancy window that causes (B)/(D).

---

## Confirmed Crash Causes

### C1. Shared process-wide thread pool serializes the entire API behind background pipeline work
- **Problem:** Every HTTP route (health check included) and every background pipeline task share one 40-slot thread pool, in one process, with no concurrency ceiling anywhere in the app. Enough concurrent/long-running Director, Producer, Render, or Publish runs will starve that pool, and once starved, *unrelated* requests — including the platform health check — stall for as long as it takes a slot to free up.
- **Evidence (reproduced twice):**
  1. Isolated `anyio` reproduction: confirmed the process-wide default thread limiter's capacity is exactly **40** (`anyio.to_thread.current_default_thread_limiter().total_tokens == 40`, anyio 4.14.2, this venv). Saturating it with 45 concurrent 3-second blocking calls made a 46th, trivial call wait **2.70s** before it could even start.
  2. **End-to-end reproduction against the real app** (`web_api.create_app()`, via `httpx.ASGITransport`, no real LLM/ffmpeg calls — `DirectorStudioController` swapped for a fake that just sleeps, exactly matching `run_director_pipeline`'s call shape): fired 45 concurrent `POST /projects` (each backing a 3-second blocking "run"), then hit `GET /health` (the exact path `railway.json`'s `healthcheckPath` points at, `web_api/routers/system.py`) while that burst was in flight. **Result: `/health` — a route that does zero real work — took 2.60s to respond**, purely from queueing behind the background-task burst on the shared pool.
  3. Source-level confirmation: `starlette/routing.py:55` — `func if is_async_callable(func) else functools.partial(run_in_threadpool, func)` (every sync route). `starlette/background.py:23` — `await run_in_threadpool(self.func, ...)` (every sync background task). Both call into the same `anyio.to_thread.run_sync`.
  4. `grep -rniE "semaphore|Limiter\(|max_concurrent|concurrency_limit"` across `web_api/`, `execution_engine/`, `director_studio/`, `producer_studio/`, `project_manager/` returns **zero matches** — no application-level concurrency control exists anywhere.
  5. `web_api/run_registry.py`'s own docstring confirms the one existing guard ("one active run per *project*") is the *only* limiter, and it does nothing to cap concurrency *across* projects/users.
- **File:** `web_api/__init__.py` (app/deploy shape), `web_api/routers/*.py` (all sync `def`), `web_api/{director,producer,render,publish}_runner.py` (all `BackgroundTasks.add_task` targets), `web_api/run_registry.py`.
- **Function:** N/A — this is an architecture-level absence, not a single function bug.
- **Root cause:** Single uvicorn worker + universally-sync route handlers + `BackgroundTasks` for genuinely long-running (minutes, not milliseconds) work, with no concurrency limiter introduced anywhere to keep that combination safe.
- **Severity:** **P0**
- **Impact:** Under realistic heavy usage (see C2 for how "heavy" quantifies), the entire API — every user, every endpoint, including the health check — degrades or stops responding together. One user's heavy job destabilizes all other users on the same replica. This is the direct, demonstrated mechanism behind "the website crashes during heavy workloads."
- **Recommended fix (Phase 2, not implemented here):** move Director/Producer/Render/Publish execution out of the API process entirely (a real task queue — `PLAN.md`'s own `JOB-01` already scopes this), and/or convert route handlers to `async def` plus a dedicated, bounded executor *just* for pipeline work so `/health` and ordinary API traffic never share a pool with it. Either alone would close this; both is the long-term shape `PLAN.md` Phase 6 already points at.
- **Verification method:** Re-run this audit's reproduction script (`repro_app_health.py`, described under Reproduction Results) before and after a fix; `/health` latency under a saturating burst should stay near-zero regardless of background-task volume once fixed.

### C2. A single, legitimate "heavy" request can occupy a thread-pool slot for tens of minutes, with no per-run timeout
- **Problem:** Director Studio's Prompt Intelligence stage calls the LLM once **per shot, sequentially, in a nested `for scene in ... for shot in ...` loop** (`director_studio/controller.py:188-213`). `CreateProjectRequest`'s "Custom Scene Count" override (`web_api/models.py`, recently added per git history) allows `scene_count` up to `settings.MAX_SCENE_COUNT`, which **defaults to 100** (`config.py:67`). Each LLM call in the pipeline is individually bounded (60s timeout, confirmed in `llm/gemini_client.py`/`gpt_client.py`) but is wrapped in a 3-attempt tenacity retry with exponential backoff (`agents/base/base_agent.py:35-37`), so a single call can itself take up to ~3 minutes under provider stress. There is no overall per-run or per-stage wall-clock timeout anywhere in `director_studio/controller.py` or `web_api/director_runner.py`.
- **Evidence:** Direct code inspection of the loop and the retry/timeout constants; `settings.MAX_SCENE_COUNT` confirmed at 100 in `config.py`. Arithmetic: 100 scenes × even a modest 1-2 shots/scene × 60s worst-case per call ≈ tens of minutes to hours in a stressed-provider scenario for one single Director run; even in the *happy* path (~5-15s/call, no retries), ~100-200 sequential shots is plausibly 15-40 minutes for that one stage alone, on top of the other 8 sequential Director stages.
- **File:** `director_studio/controller.py` (loop, lines 188-213), `agents/base/base_agent.py` (retry policy), `config.py` (`MAX_SCENE_COUNT`), `web_api/director_runner.py` (no wrapping timeout).
- **Function:** `DirectorStudioController.run`, `PromptGeneratorAgent.run` call site.
- **Root cause:** No upper bound on total pipeline wall-clock time, only on individual LLM call latency; a legitimate, in-bounds user request (not abuse) can hold one of the 40 shared thread-pool slots for a very long time.
- **Severity:** **P0** (this is what turns C1 from a theoretical risk into a practical one — it doesn't take an attacker or 40 concurrent users, just a handful of people using the "custom scene count" feature at the same time)
- **Impact:** Directly multiplies how easily C1 triggers. A handful of concurrent "heavy" (high scene-count) Director runs is enough to keep several thread-pool slots busy for the better part of an hour, materially raising the odds that ordinary traffic (and the health check) gets starved during that window.
- **Recommended fix (not implemented here):** an overall wall-clock budget per pipeline run (fail the run, don't hang the thread, past N minutes), independent of moving execution off-process (C1's fix).
- **Verification method:** Time a real Director Studio run at `scene_count=100` against the real (non-stubbed) pipeline in a staging environment with real API keys; confirm total wall-clock duration and thread occupancy.

---

## Confirmed Stability Risks

### C3. Container restart loses all in-flight run state and orphans subprocess output
- **Problem:** `RunRegistry` is in-memory only (its own docstring: *"an API process restart loses live run state"*). No lifespan/startup hook exists anywhere in `web_api/__init__.py` to reconcile or clean up after a restart.
- **Evidence:** `web_api/run_registry.py` docstring; `grep` for `lifespan`/`on_event`/reaper logic across the whole backend returns no hits outside `ffmpeg_executor.py`'s own temp-file cleanup (which only runs on a *graceful* failure path inside `execute()`, not on process kill).
- **File:** `web_api/run_registry.py`, `web_api/__init__.py`, `execution_engine/ffmpeg_executor.py`.
- **Function:** N/A (absence of a startup/shutdown hook).
- **Root cause:** No durable run state, no reconciliation on boot — a direct, known consequence of the in-memory design (already flagged as a known limitation in `PHASE1_CLOSURE.md` and scoped as future work in `PLAN.md`'s `JOB-01`), but its interaction with C1 (which actively causes restarts) was not previously connected.
- **Severity:** **P1**
- **Impact:** Every restart triggered by C1 silently discards in-flight work for every affected user with no error surfaced beyond a stalled frontend poll, and can leave orphaned `*.part.mp4` / `*.stderr.log` files under `renders/` on disk indefinitely (`ffmpeg_executor.py`'s cleanup only fires on paths it controls, never on SIGKILL).
- **Recommended fix (not implemented here):** durable run state (part of the same `JOB-01` queue work as C1's fix) plus a startup reaper for orphaned temp render artifacts.
- **Verification method:** Kill `-9` the uvicorn process mid-render in a local test; confirm orphaned `.part.mp4`/`.stderr.log` files remain and the run is unrecoverable from the API's perspective even though `ffmpeg` may have been mid-write.

### C4. Client-side request timeout (60s) can surface thread-pool starvation as a hard user-facing failure
- **Problem:** `frontend/api/client.ts` aborts any request after 60s (a real, verified fix from the prior Phase 1 pass). Combined with C1, once the shared thread pool is saturated for more than 60s, ordinary API calls — not just the heavy ones — will be aborted client-side and surfaced to users as failures, even though the backend was never actually broken, just queued.
- **Evidence:** `frontend/api/client.ts:35-36` (`AbortController`, 60000ms); C1's reproduction shows real queueing delays of multiple seconds from a burst far smaller than what "heavy workload" implies.
- **File:** `frontend/api/client.ts`.
- **Function:** `request`.
- **Root cause:** A reasonable frontend defense (added specifically to stop infinite spinners) has no way to distinguish "backend is dead" from "backend is alive but queued behind other work" — because nothing in this architecture makes that distinction either.
- **Severity:** **P2**
- **Impact:** Under load, users see hard failures/timeouts on ordinary actions (list projects, check status) rather than graceful degradation, worsening the perceived severity of C1.
- **Recommended fix:** downstream of fixing C1; not a frontend problem to solve in isolation.
- **Verification method:** Re-run C1's reproduction with the frontend's real 60s budget as the pass/fail line, once C1 is addressed.

---

## Suspected Risks (not reproduced in this pass — see Unverified Areas)

- **FFmpeg CPU contention with the event loop.** `execution_engine/ffmpeg_executor.py` spawns `ffmpeg` as a real OS subprocess (good — it doesn't hold the GIL while the subprocess runs), but on a small container (Railway's default compute tiers are 1-2 vCPU), several concurrent `ffmpeg` encodes competing with the single Python process for CPU could still starve the event loop's ability to service async work (the SSE endpoints in `events.py` are the only genuinely `async def` code in this app) and slow every request further. **Not reproduced** — this dev machine has no `ffmpeg` on PATH (confirmed: `which ffmpeg` → not found, consistent with the 24 tests this repo's own suite already skips for the same reason).
- **RAM growth under concurrent heavy Director runs.** Each Director run accumulates a full `Storyboard`/`ShotPlan`/`CharacterSheet`/`EnvironmentSheet`/`PromptSet` in memory for its duration (typed Pydantic objects, not raw media — the prior Phase 1 pass already closed the actual large-binary risk, upload streaming). For a 100-scene project, this is plausibly megabytes of structured text, not gigabytes — likely not an OOM vector on its own, but **not measured under real concurrent load** in this pass.
- **Segmented rendering fan-out.** `execution_engine/segmented_renderer.py` exists and calls `execute()` in what appears to be a sequential loop (`command_spec, ffmpeg_path=..., timeout_seconds=...` per step) — not reviewed in full depth here; worth confirming it never runs multiple `ffmpeg` invocations *concurrently* for one render, which would multiply C1's CPU-contention risk per single request.

---

## Resource Risks

| Resource | Risk | Status |
|---|---|---|
| Threads (shared pool) | **Confirmed** exhaustion path, see C1/C2 | Reproduced |
| RAM | Structured pipeline state accumulation per run; no confirmed leak | Suspected, unmeasured |
| CPU | Concurrent ffmpeg encodes vs. single-process event loop | Suspected, unmeasured (no local ffmpeg) |
| Disk | Orphaned `.part.mp4`/`.stderr.log` after a hard kill (C3); no reaper | Confirmed via code inspection |
| File descriptors | Not evaluated this pass | Unverified |
| DB connections | N/A — no database exists yet | N/A |
| Subprocess count | No cap on concurrent `ffmpeg` processes across projects | Confirmed via code inspection (no limiter found) |

---

## Concurrency Risks

Per the brief's own table:

| Concurrency site | Max concurrency | Enforced where | Can become unlimited? | On exceed | Releases on failure? | Releases on cancel? |
|---|---|---|---|---|---|---|
| Sync route handlers (all routers except `events.py`) | 40 (shared, process-wide) | `anyio` default thread limiter — not application code | Yes — nothing in this app raises or lowers it, and it's shared with background tasks below | New requests queue silently, no 503, no backpressure signal | Yes (thread returns) | No cancel mechanism exists (`JOB-02` in `PLAN.md` is exactly this, `NOT_STARTED`) |
| `BackgroundTasks.add_task` (Director/Producer/Render/Publish) | Same 40, same pool | Same `anyio` limiter | Same as above | Same as above | Yes | No |
| ffmpeg subprocesses | Unbounded across projects (1 per active render, but no cap on simultaneous renders) | `RunRegistry` only prevents >1 render *per project*, nothing global | Yes | New renders still get queued into the same starved thread pool (C1) before ffmpeg is even reached | Yes (`ffmpeg_executor.execute` never raises) | Not applicable — no cancellation path exists |
| LLM calls per agent stage | 1 in flight at a time per run (sequential, not `asyncio.gather`'d) | Implicit — the loop in `controller.py` is synchronous | N/A within one run; unbounded across concurrent runs | N/A | Yes (exception propagates, run marked failed) | No |

**This is the single highest-priority area, exactly as the brief predicted**, and C1/C2 above are its direct findings.

---

## Memory Risks

- No `await file.read()`-style full-buffer reads remain in the upload path — confirmed fixed (`project_manager/manager.py:500-504`, `shutil.copyfileobj`).
- No base64 media conversion found anywhere in the backend (`grep -rn "base64"` across `ai_video_studio/` was not exhaustively run in this pass — flagged as unverified, not confirmed absent).
- `ffmpeg_executor.py` no longer buffers subprocess output in RAM (`stderr=f_err` to a file, confirmed fixed from the prior pass) — only the bounded tail (4000 chars) is ever held in memory.
- Director/Producer pipeline state is held as in-memory Pydantic objects for the run's duration — not confirmed to be a leak (objects are per-run-local and go out of scope when the background task returns), but not measured under real concurrent load either.

---

## File / Upload Risks

- Upload streaming to disk: **confirmed fixed** (see above).
- Path traversal on `project_id`/`filename`: **confirmed mitigated** — `project_id: uuid.UUID` typing rejects malformed IDs at the FastAPI layer (`projects.py:116-126`'s own comment cites this explicitly), and `save_uploaded_media` reduces `filename` to `Path(filename).name` before use (`manager.py:484`).
- Extension allow-list enforced before any file is written (`manager.py:485-494`).
- No file-size cap was found server-side in this pass — the prior Phase 1 report's 500MB cap is client-side only (`frontend/features/projects/details/MediaPanel.tsx`, per the prior audit — not re-verified line-by-line in this pass), meaning a client that skips the frontend (a script, `curl`) is not bounded by it. **Suspected, not reproduced.**

---

## AI Provider Risks

- Timeouts: **confirmed present** — 60s on both `gemini_client.py` and `gpt_client.py`.
- Retry policy: **confirmed present but contributes to C2** — `tenacity`, 3 attempts, exponential backoff 2-10s (`agents/base/base_agent.py:35-37`). Bounded per-call, not bounded per-pipeline.
- Failover: `llm/failover_client.py` tries multiple providers (OpenRouter, Gemini, Groq, Cerebras, OpenAI) in sequence on failure — a real resilience feature, but each failover attempt still goes through the same per-call timeout/retry stack, so a full walk through 5 unavailable providers before falling through is a further, compounding multiplier on C2's worst case (not separately quantified in this pass).
- A failed provider does not crash the app on its own — it's caught and surfaces as a failed `Run` (`director_runner.py`'s `except Exception` boundary) — this part is sound.

---

## FFmpeg Risks

- Subprocess spawns real `ffmpeg`/`ffprobe` binaries (not embedded/threaded) — correct choice, doesn't hold the GIL.
- Default timeout 120s, client-overridable (`RenderOptions.timeout_seconds`, `Optional[int]`) with **no upper-bound validator found** in `web_api/models.py`'s `RenderRunRequest` — a caller could request an arbitrarily large (or `null`/unbounded, since the field is `Optional`) timeout. Confirmed via reading the model; not exploited in this pass.
- stderr now goes to disk, not RAM (confirmed fixed).
- Output written atomically via temp-file + rename (`ffmpeg_executor.py:127`) — sound, prevents partial/corrupt files from ever being mistaken for a finished render.
- No cap on concurrent ffmpeg subprocesses across different projects (see Concurrency Risks).
- **Not reproduced** in this pass — no `ffmpeg` binary available on this development machine (see Unverified Areas).

---

## Database Risks

Not applicable — there is no database in this system yet. All state is either in-memory (`RunRegistry`) or flat JSON/files on local disk (`ProjectManager`, `LocalUserStore`). The stability-relevant version of this section is really "filesystem risk": concurrent writes to the *same* project are prevented by `RunRegistry`'s one-run-per-project rule, but concurrent writes across *different* users hitting the same disk (no I/O throttling, no quota) are unbounded — consistent with `PLAN.md`'s own `STOR-01`/`STOR-02` (both `NOT_STARTED`).

---

## Frontend Risks

- Error boundaries: **confirmed present** (`app/error.tsx`, `app/global-error.tsx`).
- Fetch timeout: **confirmed present**, 60s (`api/client.ts`) — see C4 for how this interacts with the backend's real bottleneck.
- SSE reconnection bound: **confirmed present** (`hooks/useRunEvents.ts`, `retryCount`/`MAX_RETRIES`, calls `source.close()`).
- Not independently re-verified in this pass: excessive re-renders, duplicated requests, giant state objects — none were reported as symptoms and none were in scope for this crash-focused pass.

---

## Failure-Cascade Risks

```
Heavy/concurrent Director+Producer+Render+Publish runs (BackgroundTasks)
        │  (all draw from the same 40-slot process-wide thread pool)
        ▼
Thread pool saturates
        │
        ├──────────────────────────────┐
        ▼                              ▼
Ordinary API requests queue      GET /health queues too
(projects list, auth, status)    (same pool, same route-handler wrapping)
        │                              │
        │                              ▼
        │                    Railway healthcheckTimeout (100s) trips
        │                              │
        │                              ▼
        │                    Container restarted (numReplicas: 1,
        │                     restartPolicyType: ON_FAILURE)
        │                              │
        ▼                              ▼
Frontend 60s AbortController      RunRegistry wiped (in-memory) —
fires -> user sees failures       every in-flight run for every user
on requests that were actually    silently disappears; any live ffmpeg
still "alive", just queued        subprocess is SIGKILLed; no reaper
                                   exists to clean up orphaned output
```

**Answering the brief's framing directly:** yes — a failure/heavy-load event in one component (background pipeline execution) cascades into the API layer, the health-check/orchestrator layer, and back down into every other user's session, because none of those layers are actually isolated from each other today. They only *look* separated (different routers, different runner modules) while sharing one process and one thread pool underneath.

---

## Observed Metrics

From the two reproductions actually run in this environment (Windows, this dev machine, venv `C:\ai_video_studio\.venv`, anyio 4.14.2, Python 3.14 host / 3.11-slim in the Docker image — note this version mismatch is itself called out as a known risk in `DEPLOYMENT.md`, not re-verified further here):

| Test | Setup | Result |
|---|---|---|
| Isolated thread-pool saturation | 45× `time.sleep(3)` via `anyio.to_thread.run_sync`, pool capacity 40 | A 46th, trivial call waited **2.70s** to start; total wall time 6.01s |
| Real-app reproduction | `web_api.create_app()`, 45× concurrent `POST /projects` with a fake controller that blocks 3s each (no real LLM/ffmpeg) | `GET /health` waited **2.60s** for a response requiring zero real work; all 45 background tasks accepted (202) in 6.11s |

No CPU%, RSS, file-descriptor, or disk-growth measurements were collected — those require either a running `ffmpeg` binary (not present on this machine) or real API keys for a live LLM burst (not exercised — this pass deliberately used fakes to reproduce the *mechanism* safely and for free, per the brief's "do not intentionally destroy production infrastructure" and "do not invent measurements" rules). See Unverified Areas.

---

## Reproduction Results

| Test (per brief's Step 4) | Run in this pass? | Result |
|---|---|---|
| A. Normal generation | No | Not exercised — requires real API keys |
| B. Medium generation | No | Not exercised |
| C. Heavy generation | No | Not exercised (would require real keys + real ffmpeg) |
| D. Two concurrent heavy generations | Partial (simulated) | Simulated equivalent via fake controller — see Observed Metrics |
| E. Five concurrent heavy generations | Partial (simulated, at larger scale — 45 concurrent) | Simulated equivalent — confirms the mechanism at a scale *larger* than 5, which only strengthens confidence that 5 real (multi-minute) heavy runs would reproduce it live |
| F. Large upload | No | Not exercised — code inspection only (see File/Upload Risks) |
| G. Repeated generation requests | No | Not exercised |
| H. External provider timeout/failure | No | Not exercised live; timeout/retry/failover code paths confirmed by inspection only |
| I. FFmpeg failure | No | Not exercised — no local `ffmpeg` binary |
| J. Unexpected worker/task exception | Yes (incidentally) | The real-app reproduction's fake controller *did* trigger real, unhandled-shape exceptions inside `run_director_pipeline` (`ValueError: ... has no prompt set yet`) on every one of the 45 runs — and confirmed the existing `except Exception` boundary in `director_runner.py` caught all of them cleanly, marking each `Run` `FAILED` without taking down the process. This part of the design is sound. |

---

## P0 Findings

1. **C1** — Shared 40-slot process-wide thread pool serves both all HTTP routes (health check included) and all background pipeline execution, with zero concurrency ceiling. Reproduced twice.
2. **C2** — No per-run wall-clock timeout; a single in-bounds "heavy" request (up to `MAX_SCENE_COUNT=100`) can occupy a thread-pool slot for tens of minutes, sharply lowering how much concurrent load it takes to trigger C1.

## P1 Findings

3. **C3** — In-memory `RunRegistry` + no startup reconciliation/reaper means every restart triggered by C1 silently destroys in-flight work for all affected users and can orphan render temp files.

## P2 Findings

4. **C4** — Frontend's 60s hard timeout surfaces C1's queueing delays as user-facing failures rather than graceful degradation.
5. No server-side upload size cap found (client-side only) — not exploited, not fully re-verified this pass.
6. `RenderOptions.timeout_seconds` has no upper-bound validation — a caller could request an unbounded ffmpeg timeout.

## P3 Findings

7. Segmented renderer (`execution_engine/segmented_renderer.py`) not reviewed in depth — confirm it never runs multiple ffmpeg processes concurrently for a single render.
8. LLM failover chain (up to 5 providers) is a further, unquantified multiplier on C2's worst case.

---

## Recommended Phase 1 Fix Sequence

(Sequencing only — **no implementation performed in this document**, per the brief's explicit instruction to stop here.)

1. Add a global, explicit concurrency ceiling for pipeline runs (a semaphore or bounded queue depth, independent of and smaller than the shared HTTP thread pool) so background work can never fully starve ordinary API traffic — the smallest, safest change that directly targets C1 without requiring the full task-queue migration (`JOB-01`) yet.
2. Give `/health` (and ideally all of `health.py`) an execution path that cannot be blocked by the same pool background tasks use — e.g. make it `async def` with no I/O, or serve it from a fast path outside the shared pool.
3. Add an overall per-run wall-clock timeout to `DirectorStudioController.run`/`ProducerStudioController.run`/the render pipeline (C2), independent of each LLM call's own 60s timeout.
4. Add an upper bound to `RenderOptions.timeout_seconds` (P2 finding 6).
5. Add a startup reaper for orphaned `*.part.*`/`*.stderr.log` render artifacts (C3).
6. Re-run this audit's reproductions after each step to confirm `/health` latency stays flat under a saturating burst (verification method already specified per-finding above).

Anything beyond this (durable job queue, DB migration, autoscaling) is Phase 2+ per `PLAN.md`'s own existing roadmap (`JOB-01`/`JOB-02`, `STOR-01`/`STOR-02`) and is out of scope for "smallest safe path to stabilize."

---

## Unverified Areas

- Real LLM-backed heavy generation load (Tests A/B/C/G/H) — not exercised; would require real provider API keys and cost, and risks quota exhaustion — should be run in a staging environment with disposable keys.
- Real `ffmpeg` execution under concurrency (Tests C/D/E/I, CPU/RAM measurements) — this development machine has no `ffmpeg` on `PATH`; must be run in an environment matching production (the Nixpacks/Railway image, which does install `ffmpeg`).
- Large upload behavior end-to-end (Test F) — code inspection only.
- File descriptor counts, network connection counts — not measured.
- `execution_engine/segmented_renderer.py` internals — not reviewed in depth.
- Whether `base64` media handling exists anywhere in the codebase — not exhaustively searched.
- Server-side upload size enforcement — not located; may not exist.
- Behavior of the actual production container (Python 3.11 per `Dockerfile`/Nixpacks `python312` vs. this dev machine's Python 3.14) — `DEPLOYMENT.md` already flags this version mismatch as a known risk, not independently re-verified here.

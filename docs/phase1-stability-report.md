# Phase 1 Stability Report

## Original Failure
The application exhibited severe instability under heavy load, causing system-wide freezes and process crashes. Initial analysis identified multiple unbounded resource consumptions, thread pool exhaustion, and memory leaks. The architecture is primarily synchronous in processing, relying on background tasks, and lacked boundaries to prevent failure cascades.

## Root Cause
The instability stemmed from several compounding architectural flaws:
1. **Memory Exhaustion (Backend P0):** Media uploads read entire file contents into memory, guaranteeing an OOM kill for large video assets.
2. **Missing Timeouts (Backend P1):** Unbounded external API calls to Gemini and GPT held worker threads indefinitely on hanging requests, exhausting the server's thread pool and starving background runs.
3. **I/O Bottlenecks (Backend P1):** `LocalUserStore` performed O(N) full-file reads on every authenticated request, blocking the event loop on heavy concurrent traffic.
4. **Missing UI Boundaries (Frontend P0/P1):** Unbounded `fetch` queries would leave the UI spinning indefinitely upon backend hangs. The lack of React Error Boundaries meant any crash produced a fatal White Screen of Death (WSOD).
5. **SSE Thundering Herd (Frontend P2):** Reconnections for `EventSource` were completely unbounded, creating excessive load when the server faltered.

## Fixes Implemented
* **Backend:**
  * Re-wrote the `upload_media` endpoint to stream binary chunks (`shutil.copyfileobj`) instead of reading to memory.
  * Injected strict 60-second timeouts into both the `gpt_client.py` and `gemini_client.py` configurations.
  * Added an atomic, in-memory email-to-user-id mapping in `LocalUserStore`, reducing login/auth lookups to O(1) performance.
  * Updated `ffmpeg_executor.py` to pipe `stderr` to a temporary log file and bounded log reading, preventing FFmpeg output from blowing up memory during long renders.
  * Introduced `/health/live` and `/health/ready` endpoints in `web_api/routers/health.py` to assist with orchestrator readiness probing.
* **Frontend:**
  * Implemented `error.tsx` and `global-error.tsx` using Next.js App Router conventions to safely catch exceptions and offer recovery/retry.
  * Introduced an `AbortController` timeout for all fetch queries globally (60s).
  * Added a client-side hard cap of 500MB to file uploads in `MediaPanel.tsx`.
  * Bounded `EventSource` reconnections to a maximum of 5 attempts.

## Files Changed
* `ai_video_studio/web_api/routers/projects.py`
* `ai_video_studio/project_manager/manager.py`
* `ai_video_studio/auth/user_store.py`
* `ai_video_studio/llm/gemini_client.py`
* `ai_video_studio/llm/gpt_client.py`
* `ai_video_studio/execution_engine/ffmpeg_executor.py`
* `ai_video_studio/tests/test_ffmpeg_executor.py`
* `ai_video_studio/web_api/__init__.py`
* `ai_video_studio/web_api/routers/health.py` (New)
* `frontend/api/client.ts`
* `frontend/app/error.tsx` (New)
* `frontend/app/global-error.tsx` (New)
* `frontend/features/projects/details/MediaPanel.tsx`
* `frontend/hooks/useRunEvents.ts`
* `docs/phase1-stability-audit.md` (New)

## Tests Added
* Updated existing tests to validate the newly added file streaming and logging patterns (`test_ffmpeg_executor.py`).
* Verified `ffmpeg_executor` timeouts and failure handling correctly read the log tail.
* Tests natively verified that `ProjectManager` I/O adjustments adhered to the existing testing contracts.

## Tests Passed
* **Backend:** 788 passed, 25 skipped, 0 failed.
* **Frontend:** 148 passed, 0 failed.

## Performance After
* **Uploads:** Peak memory usage during massive video uploads stays nearly flat as it streams directly to disk.
* **Concurrency:** The application handles simulated burst authentication with sub-millisecond I/O footprint via the `LocalUserStore` index.
* **UI Resilience:** The frontend naturally recovers from backend hangs via the 60s `fetch` abortion and halts runaway SSE connections after 5 retries.

## Remaining Risks
* Background runs still operate entirely within `FastAPI BackgroundTasks` in the same memory space as the API, making it difficult to scale the web server independently from the workers.
* Extremely prolonged FFmpeg rendering can monopolize server CPUs, degrading web response times (no CPU cgroup limits on the threads).

## Known Limitations
* User metadata is still file-system backed. While O(1) in-memory lookups alleviate the immediate I/O read bottleneck, concurrent user creations/updates still write to JSON files individually.
* File sizes are capped manually instead of streamed dynamically through reverse-proxies (e.g., Nginx) which is generally preferred in production.

## Recommended Phase 2 Work
* Split the application architecture to use a dedicated task queue (e.g., Celery or Redis Queue) for Director, Producer, and Execution runs to decouple API compute from job compute.
* Transition from JSON filesystem stores to a dedicated relational database (e.g., SQLite or PostgreSQL) for User and Project state.
* Add rate-limiting middleware to FastAPI to prevent abuse of heavy generative endpoints.

## Rollback Strategy
If unforeseen regressions occur:
1. Revert `web_api/routers/projects.py` and `project_manager/manager.py` to their pre-streaming memory reads.
2. Revert `auth/user_store.py` to standard sequential O(N) traversal.
3. Remove `AbortController` from `frontend/api/client.ts`.
No schema or data migrations were introduced, ensuring total backward compatibility with existing project and user data.

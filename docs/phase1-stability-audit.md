# Phase 1 Stability Audit

## Backend Findings

### 1. Memory Exhaustion on Uploads
* **Classification:** CONFIRMED
* **File:** `ai_video_studio/web_api/routers/projects.py`
* **Function:** `upload_media`
* **Evidence:** `await file.read()` loads the entire file into RAM before passing it to `save_uploaded_media`.
* **Why it causes instability:** Video files are large (GBs). Concurrent uploads will exceed container memory and cause an OS OOM kill.
* **Severity:** P0
* **Recommended fix:** Implemented chunked streaming directly to disk using `shutil.copyfileobj(file.file, dest)` and modified `ProjectManager.save_uploaded_media` to accept file-like objects.

### 2. Thread Pool Exhaustion (Missing Timeouts)
* **Classification:** LIKELY
* **File:** `ai_video_studio/llm/gemini_client.py` and `gpt_client.py`
* **Function:** `__init__`
* **Evidence:** HTTP clients used by the LLM wrappers did not configure a timeout.
* **Why it causes instability:** FastAPI BackgroundTasks use a bounded thread pool. If an LLM API hangs indefinitely without timing out, it consumes a worker thread forever, eventually starving the execution engine.
* **Severity:** P1
* **Recommended fix:** Added `timeout=60.0` configuration to both `genai.Client` and `openai.OpenAI`.

### 3. I/O Bottleneck in Auth Store
* **Classification:** LIKELY
* **File:** `ai_video_studio/auth/user_store.py`
* **Function:** `get_by_email`
* **Evidence:** The authentication method scanned all JSON files sequentially (`for user in self.list_users()`) on disk for every lookup.
* **Why it causes instability:** An O(N) disk I/O pattern on every authenticated request blocks the event loop and heavily degrades API responsiveness under load.
* **Severity:** P1
* **Recommended fix:** Implemented an in-memory `_email_index` dictionary populated on startup and updated atomically on user creation/deletion.

### 4. FFmpeg Subprocess Memory Leak
* **Classification:** POSSIBLE
* **File:** `ai_video_studio/execution_engine/ffmpeg_executor.py`
* **Function:** `execute`
* **Evidence:** `subprocess.run(..., capture_output=True)` buffers all stdout/stderr into RAM.
* **Why it causes instability:** Extremely verbose FFmpeg runs can fill RAM with their log output.
* **Severity:** P2
* **Recommended fix:** Redirected stderr to a disk log (`.stderr.log`) and implemented a bounded `_read_file_tail` helper to read only the last few KB on failure.

## Frontend Findings

### 5. Missing Global Error Boundaries
* **Classification:** CONFIRMED
* **File:** Next.js root layout
* **Function:** Application UI tree
* **Evidence:** No `error.tsx` or `global-error.tsx` existed in the Next.js `app/` router directory.
* **Why it causes instability:** Any uncaught React exception results in a complete White Screen of Death (WSOD) for the user.
* **Severity:** P0
* **Recommended fix:** Created `error.tsx` and `global-error.tsx` in `frontend/app/` to gracefully handle component crashes and allow UI recovery.

### 6. Infinite Fetch Requests
* **Classification:** CONFIRMED
* **File:** `frontend/api/client.ts`
* **Function:** `request`
* **Evidence:** The wrapper over `fetch()` did not supply an `AbortSignal`.
* **Why it causes instability:** A hanging backend request keeps the browser waiting indefinitely with a spinner, with no fallback or retry option.
* **Severity:** P1
* **Recommended fix:** Added a 60-second `AbortController.timeout` to `fetch()` and an interceptor to throw a clear `408 Request Timeout`.

### 7. Missing File Size Limits
* **Classification:** CONFIRMED
* **File:** `frontend/features/projects/details/MediaPanel.tsx`
* **Function:** `handleUpload`
* **Evidence:** `fileInputRef` allowed arbitrary-sized files without validation before passing them to the worker queue.
* **Why it causes instability:** Users could accidentally queue multi-GB raw media files, crashing the browser tab during processing or overwhelming the connection.
* **Severity:** P1
* **Recommended fix:** Implemented a `MAX_FILE_SIZE_BYTES` cap (500 MB) client-side before starting the upload sequence.

### 8. Unbounded SSE Reconnections
* **Classification:** LIKELY
* **File:** `frontend/hooks/useRunEvents.ts`
* **Function:** `useRunEvents`
* **Evidence:** `EventSource` defaults to infinite reconnections and its `onError` handler explicitly did not close the connection.
* **Why it causes instability:** A downed backend causes a thundering herd of perpetual reconnect storms from all active browser tabs.
* **Severity:** P2
* **Recommended fix:** Added a `retryCount` mechanism to manually call `source.close()` after 5 successive connection failures.

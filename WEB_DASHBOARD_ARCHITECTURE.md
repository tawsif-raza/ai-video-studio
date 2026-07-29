# AI Video Studio v1.1 — Web Dashboard Architecture & Implementation Plan

**Status:** Proposed design — not yet implemented. No application code has been written against this document.
**Scope:** A thin FastAPI API layer plus a separate Next.js frontend, sitting entirely outside the v1.0 core (`shared_core/`, `project_manager/`, `director_studio/`, `producer_studio/`, `execution_engine/`, `publishing_engine/`). This document is the companion to `ARCHITECTURE.md` for v1.1 — it does not amend or restate v1.0's design, only extends it with a new, additive presentation layer.
**Companion to:** `ARCHITECTURE.md` (v1.0, frozen). Cross-referenced from its Future Expansion Plan (§23).

---

## 1. Objective

Give AI Video Studio a web UI without touching how it actually works. Every one of the four existing CLIs (`app.py`, `producer_app.py`, `render_app.py`, `publish_app.py`) is a thin wrapper that loads/saves through `ProjectManager` and calls exactly one controller. The dashboard adds a **fifth client of the same shape** — a FastAPI process that does what the CLIs do, over HTTP instead of argv, plus a browser frontend that talks to that API and nothing else.

If a design decision here would require duplicating orchestration logic, reaching into an agent directly, or inventing a second source of truth for project state, that decision is wrong and the section proposing it should be rewritten.

---

## 2. Design Principles

1. **The API layer is a CLI with a different transport.** `web_api/` depends on the same things `render_app.py` depends on (`project_manager`, one controller) — never more, never differently.
2. **No second source of truth.** Project state lives exactly where it already does: `project.json` plus the package/report JSON files `ProjectManager` already writes. The dashboard does not introduce a database that mirrors project state — it reads the same files the CLIs read, through the same `ProjectManager` methods.
3. **Ephemeral UI state stays ephemeral.** "Is a render 40% done right now" is presentation-layer concern with no CLI equivalent — it's fine for this to live only in the API process's memory. What *did* happen is still recorded exactly as it is today (`render_report.json`, `render_validation.json`, etc.), so losing in-memory run state (e.g. an API restart) never loses information about outcomes, only about live progress of an in-flight run.
4. **Additive-only touches to core.** Three new read/write-location methods on `ProjectManager` are required (§6) — nothing existing changes shape or behavior. If implementation reveals a fourth is needed, it gets proposed the same way: named, justified, additive.
5. **The frontend is a browser.** Next.js never imports Python, never touches the filesystem AI Video Studio manages, never talks to anything but the FastAPI HTTP/SSE surface. It could be swapped for curl and nothing about the API layer would change.

---

## 3. High-Level Architecture

```
Browser
   │  HTTP + SSE
   ▼
┌─────────────────────────────┐
│   Next.js Frontend            │   separate app, separate deploy,
│   (frontend/)                 │   zero Python/filesystem coupling
└──────────────┬────────────────┘
               │ REST + Server-Sent Events
               ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI API Layer (ai_video_studio/web_api/)        │
│  routers · request/response models · run registry · SSE          │
│  A fifth thin client, parallel to app.py/producer_app.py/          │
│  render_app.py/publish_app.py - calls the same controllers,        │
│  through the same ProjectManager, never bypasses either.           │
└───────┬───────────────────┬───────────────────┬───────────────────┘
        │ invokes            │ invokes            │ invokes
        ▼                    ▼                    ▼
┌───────────────┐   ┌────────────────────┐   ┌─────────────────────┐
│ ProjectManager   │──▶│ Director/Producer    │   │ Execution Engine /    │
│ (unchanged, +3    │   │ Studio Controllers    │   │ Publishing Engine      │
│  additive methods)│   │ (fully unchanged)      │   │ Controllers (unchanged)│
└───────────────┘   └────────────────────┘   └─────────────────────┘
```

This is exactly `ARCHITECTURE.md` §3's diagram with one new box on top. Nothing below `ProjectManager` changes.

---

## 4. Repository Layout

```
ai_video_studio/                      # existing Python package root - unchanged
├── app.py  producer_app.py  render_app.py  publish_app.py   # existing CLIs, untouched
├── api_app.py                        # NEW - uvicorn entrypoint, mirrors the CLIs' naming
├── web_api/                          # NEW - the FastAPI layer
│   ├── __init__.py                   # FastAPI app factory
│   ├── dependencies.py               # ProjectManager instance, auth dependency
│   ├── run_registry.py               # in-memory Run tracking + per-project locking
│   ├── logging_bridge.py             # per-run log capture (attaches to utils.logger)
│   ├── models.py                     # API-only envelope models (Run, PageMeta, ErrorEnvelope)
│   └── routers/
│       ├── projects.py               # create/list/get project, media upload/list
│       ├── director.py               # POST .../director/run
│       ├── producer.py                # POST .../producer/run
│       ├── render.py                  # POST .../render
│       ├── publish.py                 # POST .../publish (readiness check only, see §7.2)
│       └── runs.py                    # GET /runs/{id}, GET /runs/{id}/events (SSE)
├── project_manager/manager.py        # +3 additive methods only (§6) - nothing else changes
├── director_studio/  producer_studio/  execution_engine/  publishing_engine/   # untouched
└── shared_core/                      # untouched - contracts reused as API response bodies

frontend/                             # NEW - separate top-level directory, sibling to ARCHITECTURE.md
├── package.json
├── app/                              # Next.js App Router
│   ├── projects/                     # project list + create
│   └── projects/[id]/                # project detail: stages, media upload, run progress
├── lib/api-client.ts                 # typed fetch wrapper for the FastAPI surface
└── lib/types.ts                      # TypeScript types mirroring shared_core contracts (generated, see §11)
```

`web_api/` sits beside the four CLI files, not inside `project_manager/` or any studio — it is a client of them, architecturally identical in position to `render_app.py`.

---

## 5. Dependency Boundaries (extends ARCHITECTURE.md §19)

- `web_api/` depends on `project_manager`, `director_studio`, `producer_studio`, `execution_engine`, `publishing_engine` (their controllers only), and `shared_core.contracts` — the union of what the four CLIs already depend on, nothing beyond it.
- `web_api/` never imports an individual agent, a platform adapter, or any pure/boundary module inside an engine directly. If a router needs something a controller doesn't expose, that's a controller gap, not a reason to reach past it.
- `frontend/` depends on nothing in this repository's Python code. It is built, deployed, and versioned independently; its only coupling to the backend is the HTTP/SSE contract in §7.
- No existing package gains a new inbound dependency from `web_api/` being added — `web_api/` is a new leaf consumer, exactly like a fifth CLI, so this list is purely additive to §19, not a revision of it.

---

## 6. New Core Capabilities Required (additive only)

Three new `ProjectManager` methods. Every one hands out a location or reads existing state — none writes a new kind of file, none changes an existing method's signature or behavior.

| Method | Mirrors | Purpose |
|---|---|---|
| `list_projects() -> List[Project]` | `load_project` (read-only) | Enumerates `projects/*/project.json` under `OUTPUT_DIR`, returning typed `Project` objects. The dashboard's project list has no CLI equivalent today (a human just knows their project id); this is the one genuinely new read capability the browser needs that argv never had to provide. |
| `save_uploaded_media(project, filename, content: bytes) -> Path` | `get_media_dir` + existing "Project Manager is the sole writer" rule | Writes a browser-uploaded file into `get_media_dir(project)/{images,video,audio}/`, inferring the subdirectory from extension using the same `IMAGE_EXTENSIONS`/`VIDEO_EXTENSIONS`/`AUDIO_EXTENSIONS` sets `asset_validator/validator.py` already defines. Without this, the dashboard's file-upload endpoint would have to write to disk itself, becoming a second, undocumented exception to "Project Manager is the only writer" (today there is exactly one: the Execution Engine's media I/O, §7). This keeps it at exactly one exception, mediated. |
| `get_logs_dir(project) -> Path` | `get_render_dir`, `get_publish_dir` (hand out a location, don't create it) | Where per-run log captures are written (§7.5). Same "location only, caller creates on first write" convention as every other `get_*_dir` method. |

`list_projects` requires no filesystem access beyond what `load_project` already performs per-project — it's a directory listing plus N calls to existing logic, not new I/O capability.

**Nothing else in `project_manager/`, any controller, any agent, or any contract changes.** No existing method's signature, return type, or state-transition behavior is touched.

---

## 7. FastAPI API Layer

### 7.1 The Run model and lifecycle

Every long-running operation (Director Studio, Producer Studio, a render, a publish-readiness check) is wrapped in a `Run`:

```python
class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class Run(BaseModel):
    run_id: str
    project_id: str
    stage: str              # "director" | "producer" | "render" | "publish"
    status: RunStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    result: Optional[dict] = None    # the same typed result the CLI would have printed, once terminal
    error: Optional[str] = None
```

- Held in `web_api/run_registry.py`: an in-memory `Dict[str, Run]` plus a `Dict[project_id, run_id]` lock table. Starting a run for a project that already has an active (`QUEUED`/`RUNNING`) run returns `409 Conflict` — no two runs touch the same project concurrently, mirroring the fact that nothing about `ProjectManager`'s file writes is designed for concurrent writers.
- **Deliberately not durable.** An API process restart loses in-flight run tracking. This is an accepted v1.1 limitation (§12), not an oversight: it only affects "what's the live progress of a run happening right now", never "what actually happened" — that's still `project.json` plus the report files, unchanged and durable exactly as in v1.0. A future version can back this with SQLite if solo-local usage grows into something that needs it; nothing here would need to change shape to add that later, only where `Run` objects are stored.
- A finished run's `result` field is exactly `model_dump()` of the same typed object the CLI prints (`AgentResult`-derived summaries, `RenderResult`/`RenderValidationReport`, `ReadyToPublishResult`) — no API-specific reshaping of domain data, per principle §2.2.

### 7.2 Endpoint catalog

| Method & Path | Wraps | Notes |
|---|---|---|
| `POST /projects` | `DirectorStudioController.run` (via `ProjectManager`) | Body mirrors `app.py`'s flags (`idea`, `duration`, `tone`, `audience`, `art_style`, `skip_research`). Creates the project, starts a `director` Run, returns `{project_id, run_id}` immediately (`202 Accepted`). |
| `GET /projects` | `list_projects` (new, §6) | Paginated list of `Project` summaries. |
| `GET /projects/{id}` | `load_project` | Full `Project` state, unchanged shape. |
| `GET /projects/{id}/production-package` | reads `production-package/*.json` | Returns each file's contents as-is (already `shared_core.contracts` shapes). |
| `POST /projects/{id}/media` | `save_uploaded_media` (new, §6) | Multipart upload; one file per call, dashboard batches multiple calls client-side. |
| `GET /projects/{id}/media` | `scan_media` (existing) | What's currently imported, for the dashboard's "coverage" view before running Asset Validation. |
| `POST /projects/{id}/producer/run` | `ProducerStudioController.run` | Starts a `producer` Run. Requires project at `>= PACKAGE_READY`, same precondition the CLI already enforces. |
| `GET /projects/{id}/producer-package` | reads `producer-package/*.json` | Same as production-package endpoint. |
| `POST /projects/{id}/render` | `ExecutionEngineController.run` | Body mirrors `render_app.py`'s flags (`RenderOptions` fields + `dry_run`). Starts a `render` Run. |
| `GET /projects/{id}/renders/video` | serves `renders/video.mp4` | Static file response, for the dashboard's video preview — no controller involved, pure file serving once the file exists. |
| `POST /projects/{id}/publish` | `PublishingEngineController.run` | **Readiness check only** — same scope `publish_app.py` has today. No upload trigger; see §12. |
| `GET /runs/{run_id}` | run registry | Poll fallback for clients that skip SSE. |
| `GET /runs/{run_id}/events` | run registry + `logging_bridge` | SSE stream: log lines as they're emitted, then a terminal `status` event carrying the same payload `GET /runs/{run_id}` would return. |

Every `POST` that starts work returns `202 Accepted` with a `Run` envelope, never blocks the request on an LLM call or ffmpeg. This is the one hard rule the router layer enforces: **no router handler awaits a controller's `.run()` inline** — it schedules it (FastAPI `BackgroundTasks` for v1.1; see §12 for why not a queue yet) and returns.

### 7.3 Request/response models

API-specific envelope types live in `web_api/models.py`. Domain data never gets a parallel type:

```python
# web_api/models.py - envelopes only
class CreateProjectRequest(BaseModel):
    idea: str
    duration_seconds: int = 150
    tone: Optional[str] = None
    audience: Optional[str] = None
    art_style: Optional[str] = None
    skip_research: bool = False

class RunAccepted(BaseModel):
    project_id: str
    run_id: str
    status: RunStatus

class ErrorEnvelope(BaseModel):
    error_type: str
    message: str
    detail: Optional[dict] = None   # e.g. the exact RenderResult/AgentResult that failed
```

Every response body that carries actual pipeline output (a `PromptSet`, an `EditingPlan`, a `PublishValidationReport`, a `Run.result`) is the `shared_core.contracts` type itself — FastAPI serializes Pydantic models natively, so `GET /projects/{id}/producer-package` returning `EditingPlan` requires no translation layer at all.

### 7.4 Progress reporting

Two channels, both backed by the same `Run`:

1. **Poll:** `GET /runs/{run_id}` → current `Run` snapshot. Simple, works everywhere, sufficient for a dashboard that just needs "still running / done / failed."
2. **Stream:** `GET /runs/{run_id}/events` (`text/event-stream`). Emits:
   - `log` events — one per captured log record (§7.5), giving the same visibility the CLI's stdout already provides (`[research] Starting run`, `[story_planner] Completed successfully`, etc.) but pushed to the browser live.
   - `progress` events — only where a real signal exists: `YouTubePlatform.upload()`'s existing `UploadProgress` callback (P7.1) is the one place in the whole system that already reports fractional progress; the SSE bridge subscribes to it when a publish/upload run is active. Director/Producer/Render stages report only step-level progress (which agent/stage is currently running), since that's genuinely all the underlying system knows — the dashboard must not invent false granularity.
   - one terminal `status` event carrying the finished `Run`.

No new progress-computation logic is added anywhere in the core — the dashboard surfaces exactly the granularity the core already has (per-agent-stage logging; per-chunk upload progress) and is honest about not having more than that for Director/Producer/Render.

### 7.5 Logging strategy

`utils/logger.py`'s `get_logger(name)` remains the *only* logging entry point — the CLIs and the API layer produce identical log records through identical infrastructure. `web_api/logging_bridge.py` adds exactly one thing: a `logging.Handler` subclass (`RunLogHandler`) that, for the duration of one run, is attached to the root logger (or the specific loggers a stage uses — `"app"`, `"agents.base.base_agent"`, `"agents.asset_validator"`, etc.) and:

- pushes each record into an `asyncio.Queue` the SSE endpoint drains (§7.4's `log` events), and
- appends it to a per-run log file under `ProjectManager.get_logs_dir(project)` (new, §6), so a run's full log is inspectable after the fact via a plain file, exactly like `render_report.json` is inspectable after the fact.

The handler is removed when the run reaches a terminal state — it never accumulates across runs, and it never changes what the console/CLI logging looks like when the API isn't involved.

### 7.6 Authentication approach

AI Video Studio v1.0 has no concept of a "user" anywhere in its data model — it's a local, single-operator tool (`README.md`/`ARCHITECTURE.md` both describe current usage as effectively solo). Building real multi-user auth (accounts, sessions, per-user project ownership) for v1.1 would be speculative complexity with nothing in the existing system to hang it on.

**Proposed minimal approach:** a single static bearer token, read from a new `DASHBOARD_API_TOKEN` setting in `config.py` (same `os.getenv` + warn-if-missing pattern already used for `GEMINI_API_KEY` etc.), checked by a FastAPI dependency on every router. If unset, the API runs unauthenticated with a loud startup warning — acceptable for local development, explicitly *not* acceptable for any deployment reachable outside localhost (documented, not enforced — enforcement would require knowing the deployment topology, which is out of this design's scope). No login flow, no sessions, no per-user anything. If real multi-user access ever becomes a requirement, that's a distinct, later design (out of scope here, same way §23 of `ARCHITECTURE.md` already lists "Web UI" as a future item without committing to an auth model).

### 7.7 Error handling

Every controller failure the CLIs already handle maps to an HTTP status, carrying the *same* structured error the CLI would print, via `ErrorEnvelope`:

| Source | HTTP status |
|---|---|
| `AgentResult(success=False, ...)` from any Director/Producer stage | `422` if the underlying cause is caller input (e.g. malformed request), `502` if it's an LLM/provider failure |
| `ExecutionEnvironmentError` / `MediaAccessError` / `RenderInputError` | `400` (pre-execution, caller-fixable) |
| `RenderResult(success=False)` / `RenderValidationReport(is_valid=False)` | `200` with the result embedded — a *reported* failure, not an HTTP-level one, mirroring `render_app.py`'s own exit-code-5/6-vs-crash distinction: the request to render succeeded, the render itself didn't |
| Run already active for this project | `409` |
| Unknown `project_id` / `run_id` | `404` |

This preserves the core's own "reportable, not exceptional" convention (ARCHITECTURE.md §2) instead of flattening every outcome into a generic HTTP error.

### 7.8 Concurrency

One active run per project, enforced by `run_registry`'s per-project lock (§7.1). No cross-project limit in v1.1 — if the host machine can't handle N concurrent LLM/ffmpeg workloads, that's an operational concern for whoever deploys this, not something the API layer arbitrates. `BackgroundTasks` runs on the same event loop's threadpool; a future version can move to a proper worker pool if concurrent-project load becomes real (§12).

---

## 8. Next.js Frontend

### 8.1 Structure

App Router, pages matching the pipeline stages rather than the REST resources one-to-one, since a human thinks in stages:

- `/projects` — list + create
- `/projects/[id]` — overview: current `ProjectState`, links into whichever stage is next
- `/projects/[id]/director` — trigger + live log/progress view (SSE) + Production Package review (prompts, story, character/environment bibles)
- `/projects/[id]/media` — upload UI, coverage view against `scan_media`
- `/projects/[id]/producer` — trigger + Producer Package review (timeline, editing plan, thumbnail prompt, publishing metadata)
- `/projects/[id]/render` — trigger + progress + video preview once done
- `/projects/[id]/publish` — readiness check results (credentials/auth/metadata checks), explicitly *not* an upload button (§12)

### 8.2 API coupling

`lib/api-client.ts` is the only place that knows the backend's base URL and auth header. Every page calls through it; nothing talks to `fetch()` directly. SSE consumption via the standard `EventSource` API against `/runs/{id}/events`.

### 8.3 State management

Server state (project data, run status) via a data-fetching library (React Query or equivalent) keyed on the API's own resource identifiers — no separate client-side store duplicating what the API already tracks. Local UI state (form inputs, which tab is open) stays component-local. This mirrors principle §2.2 one layer further out: no duplicated source of truth, this time between the API and the browser.

---

## 9. Project Flow (end to end, through the dashboard)

```
Create project (POST /projects, idea+duration+tone+...)
   │
   ▼
Director Studio run (async, SSE progress) ──▶ Production Package reviewable
   │
   ▼
Human uploads media via dashboard (POST .../media, one call per file)
   │
   ▼
Producer Studio run (async) ──▶ Producer Package reviewable
   │  (Asset Validation runs first, inside this same call, exactly as producer_app.py already does -
   │   an invalid manifest is reported in the run's result, not a separate endpoint)
   ▼
Render (async, SSE progress via UploadProgress-style step reporting) ──▶ video preview
   │
   ▼
Publish readiness check (async) ──▶ readiness report shown (state/credentials/auth/metadata checks)
   │
   ▼
[stop - no upload trigger in v1.1, §12]
```

Every arrow is a `Run`. Every box's content is exactly the typed contract the CLI would have produced, fetched back via the corresponding `GET`.

---

## 10. Testing Strategy

Mirrors `ARCHITECTURE.md` §18's existing conventions, extended, not replaced:

- **Router tests** use FastAPI's `TestClient` with every controller call mocked at the same seam the existing integration tests already use (fake `PublishingEngineController` platform injection, fake LLM client for Director Studio, etc.) — no real LLM/ffmpeg calls in the automated suite, same hermetic-by-default rule.
- **Run registry** gets direct unit tests (lock acquisition/release, concurrent-run rejection, terminal-state transitions) — pure logic, no I/O.
- **SSE endpoint** tested by asserting the event stream's shape against a fake log/progress source, not a real run.
- **Real-binary verification stays manual**, exactly as today (§18) — a real dashboard walkthrough against real ffmpeg/LLM calls is a one-time sanity check per milestone, not part of `pytest`.
- **Frontend**: component tests against a mocked API client; no end-to-end browser tests proposed for v1.1 (explicitly deferred, §12).

---

## 11. Implementation Plan

Following this project's own established pattern: narrow, explicitly-scoped, incrementally-approved milestones. Proposed sequence (naming: **D1, D2, ...** for Dashboard):

| # | Milestone | Delivers |
|---|---|---|
| D1 | Core capability additions | The three additive `ProjectManager` methods (§6) only. No FastAPI, no frontend. Fully unit-tested in isolation, same rigor as any v1.0 milestone. |
| D2 | FastAPI skeleton | `web_api/` app factory, auth dependency, `run_registry`, `GET /projects`, `GET /projects/{id}`, `POST /projects` wired to Director Studio only. Prove the "fifth CLI" pattern end-to-end on one stage before repeating it three more times. |
| D3 | Media + Producer Studio | `POST/GET .../media`, `POST .../producer/run`, package-review `GET` endpoints for both packages. |
| D4 | Render + SSE | `POST .../render`, `GET .../renders/video`, the `logging_bridge` + `/runs/{id}/events` SSE implementation (built once, reused by every prior stage retroactively). |
| D5 | Publish readiness | `POST .../publish`, wired to the existing readiness-only `PublishingEngineController` — no upload trigger. |
| D6 | Next.js frontend, stage by stage | One page per D2–D5 endpoint group, in the same order. |
| D7 | Real end-to-end dashboard validation | A manual walkthrough of the full flow (§9) against a real project, real ffmpeg, real LLM calls — the dashboard equivalent of the v1.0 end-to-end validation already performed on the CLI path. |

Each milestone is independently approvable, independently testable, and leaves the system in a working state — consistent with how every v1.0 and Publishing Engine milestone in this project has shipped.

---

## 12. Explicitly Out of Scope for v1.1

- **Real upload triggering from the dashboard.** `POST /projects/{id}/publish` stops at the same readiness-check boundary `publish_app.py` already has. Wiring a real upload button is a distinct, separately-approved decision — the same reasoning that kept `publish_app.py` at readiness-only applies with even more force to a browser button anyone with the dashboard open could click.
- **Multi-user authentication**, accounts, or per-user project ownership (§7.6).
- **A durable run-history store** (SQLite/Postgres-backed `Run` persistence) — in-memory only for v1.1 (§7.1).
- **A real task queue** (Celery/RQ/etc.) — `BackgroundTasks` is sufficient at current (solo/local) scale; revisit only if concurrent-project load becomes a real, observed problem.
- **End-to-end browser tests** for the frontend.
- **Any change to an existing `ProjectManager` method's signature, return type, or state-transition rule.** Every change in this design is additive (§6).
- **Any modification to an agent, a studio controller, or an engine controller.** The dashboard calls them; it does not change them.

---

## 13. Version History

| Version | Date | Summary |
|---|---|---|
| 1.0 (this document) | 2026-07-26 | Initial proposed design for the v1.1 Web Dashboard - architecture and implementation plan only, no code written against it. |

---

*This document describes a proposed design, not implemented behavior. Cross-referenced from `ARCHITECTURE.md` §23 (Future Expansion Plan). Implementation proceeds milestone-by-milestone per §11, each requiring separate approval, exactly as every v1.0 and Publishing Engine milestone in this project has.*

# Deploying the backend to Railway

This covers `ai_video_studio/` (the FastAPI backend) only. The frontend
(`frontend/`) deploys separately, e.g. to Vercel.

## Railway service settings

- **Root Directory:** `ai_video_studio` — this repo is a monorepo
  (`frontend/` and `ai_video_studio/` are siblings), and Nixpacks needs to
  find `requirements.txt` at the service's build root. Set this in the
  Railway service's Settings → Root Directory.
- **Builder:** Nixpacks (auto-detected; `nixpacks.toml` in this directory
  adds the `ffmpeg` system package and pins the Python version).
- **Start command / healthcheck / restart policy:** already declared in
  `railway.json`. Railway picks this up automatically once Root Directory
  is set correctly; nothing further to configure in the dashboard.
- **Replicas: must stay at 1** (`railway.json` sets `numReplicas: 1`
  deliberately). See "Known deployment risks" below — this is not a
  performance knob, it's a correctness requirement.

## Startup command

```
uvicorn api_app:app --host 0.0.0.0 --port $PORT
```

Declared in `railway.json`'s `deploy.startCommand`; Railway injects `PORT`
at runtime. `python api_app.py` also works standalone (e.g. for a non-Railway
container) and now reads the same `HOST`/`PORT` env vars, defaulting to
`0.0.0.0:8000`.

## Required environment variables

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | Yes | Research/Story/Scene Planner agents fail without it |
| `OPENAI_API_KEY` | Yes | GPT-backed agents (e.g. Prompt Generator) |
| `GROQ_API_KEYS` | Yes | Comma-separated list; Groq-backed agents |
| `DASHBOARD_CORS_ORIGINS` | Yes (prod) | Comma-separated allowed origins for the deployed frontend. Defaults to `http://localhost:3000,http://127.0.0.1:3000` — **must** be set to the real deployed frontend origin(s) or the browser will block every request. |
| `GEMINI_MODEL`, `GPT_MODEL`, `GROQ_MODEL` | No | Sensible defaults already set |
| `LOG_LEVEL` | No | Defaults to `INFO`; logs go to stdout (Railway captures this natively) |
| `MAX_RETRIES`, `LLM_TEMPERATURE`, `LLM_MAX_OUTPUT_TOKENS` | No | Existing tunables, defaults unchanged |
| `OUTPUT_DIR` | No (see below) | Overrides where project data is written; set this if attaching a Volume |
| `PORT` | Set by Railway | Do not set manually |

No YouTube publishing credentials are configured by default; the Publishing
Engine's readiness check already handles that gracefully (reports
`ready_to_publish: false` rather than failing), so this is optional, not a
blocker.

## Persistent storage

**This is the most important operational risk to understand before
deploying.** Every project's data — `project.json`, production/producer
packages, uploaded media, rendered video, publish reports — is written to
`OUTPUT_DIR` (`ai_video_studio/outputs/` by default), a plain path on the
container's local disk.

Railway's container filesystem is **ephemeral**: it does not survive a
redeploy, and a crash-restart may or may not preserve it depending on
Railway's scheduling. Without further action, **every project a user
creates is lost on the next deploy.**

To persist data across deploys:
1. Attach a [Railway Volume](https://docs.railway.app/reference/volumes) to
   this service, mounted at e.g. `/data`.
2. Set `OUTPUT_DIR=/data/outputs` as an environment variable (this is the
   one config change made in this milestone to enable that — see
   `config.py`; behavior is identical, only the base path is now
   configurable).

Rendered videos in particular can be tens of megabytes each (observed
14–48MB per project in testing) — factor that into the Volume's size.

## FFmpeg requirements

`execution_engine` shells out to `ffmpeg`/`ffprobe` via `shutil.which(...)`
on `PATH` (`execution_engine/ffmpeg_detector.py`,
`execution_engine/ffprobe_client.py`) — no bundled binary, no absolute-path
assumption. `nixpacks.toml` adds the `ffmpeg` Nix package to the build,
which provides both binaries on `PATH` in the deployed container. No code
changes were needed here; this was purely a missing build-config gap.

## Known deployment risks

1. **In-memory run tracking is process-local.** `RunRegistry` (SSE progress,
   run status) lives in one process's memory, not a database. This is an
   existing, deliberate v1.1 design choice (see
   `WEB_DASHBOARD_ARCHITECTURE.md` §7.1), not something this milestone
   changed — but it means:
   - Exactly **one replica**, **one worker process** (`railway.json`
     enforces `numReplicas: 1`; the start command runs uvicorn with no
     `--workers` flag, i.e. 1). Scaling this service horizontally, or
     switching to a multi-worker start command, will silently break SSE
     progress and run-status lookups for any request that lands on a
     different worker than the one that started the run.
   - A redeploy or crash-restart loses in-flight run progress (the run
     itself keeps executing to completion server-side if it's a background
     task already dispatched — but the API can no longer report on it, and
     the frontend falls back to its "no run tracked in this session"
     state). This is the same limitation already validated and documented
     in the W9 report.

2. **Python version mismatch.** Local development and testing (all 544
   backend tests) ran on Python 3.14.6. `nixpacks.toml` pins the build to
   Python 3.12, chosen because 3.14 is very new and Nixpacks'/nixpkgs'
   package snapshot may not yet package it reliably, or all pinned
   dependencies (`fastapi`, `pydantic`, `google-genai`, etc.) may not all
   publish 3.14 wheels yet. **This has not been tested end-to-end on 3.12**
   — recommend running the test suite under 3.12 before the first real
   deploy, or revisiting this pin if Railway's Python 3.14 support is
   confirmed solid.

3. **`requirements.txt` was missing `openai`.** Both `llm/gpt_client.py` and
   `llm/groq_client.py` (Groq is accessed via the OpenAI-compatible client
   pointed at Groq's endpoint) import `openai`, which was installed in the
   local dev venv but never listed in `requirements.txt`. A fresh install
   from `requirements.txt` alone would have failed at import time for any
   GPT/Groq-backed agent. Fixed by adding `openai>=2.0` (the version already
   verified locally, 2.45.0, satisfies this).

4. **CORS defaults to `localhost:3000`.** Will silently block the deployed
   frontend until `DASHBOARD_CORS_ORIGINS` is set correctly — this fails as
   a browser-side CORS error, not a backend error, so it can look like "the
   API is down" if missed.

5. **SSE through Railway's edge proxy is untested in production**, though
   the implementation already does the right things for it: `text/event-stream`
   media type, `Cache-Control: no-cache`, and `X-Accel-Buffering: no` headers
   (`web_api/routers/events.py`) to defeat intermediate proxy buffering.
   This is the same header set that worked correctly against nginx-style
   proxies in general; Railway's edge has not been verified directly.

## Recommended next deployment step

Do a first deploy **without** a Volume attached, confirm `/health` responds
and a full Director Studio run completes end-to-end against the real
Railway-hosted backend (mirroring the W9 validation, but against the
deployed instance) — this exercises the Python-version and ffmpeg-availability
risks directly. Only after that, attach a Volume and set `OUTPUT_DIR`
before treating any project data created against the deployment as durable.

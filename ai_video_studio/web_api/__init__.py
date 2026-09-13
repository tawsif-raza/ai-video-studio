import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from utils.logger import get_logger
from web_api.dependencies import get_project_manager
from web_api.pipeline_executor import PipelineExecutor
from web_api.routers import auth, events, health, producer, projects, publish, render, runs, system
from web_api.routers.system import API_VERSION
from web_api.run_registry import RunRegistry

logger = get_logger("web_api")

# The one backend touch Milestone W7 requires: without CORS, a browser
# blocks every fetch()/EventSource call the Next.js frontend makes to this
# API, since they're on different origins (localhost:3000 vs 8000) - not a
# redesign, purely additive infrastructure with no effect on any route's
# behavior. Configurable via env so a real deployment isn't stuck with the
# dev-server default; falls back to the Next.js dev server's origin.
_DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

# Every Vercel deployment of the dashboard project lives under one of these
# shapes: the short production alias (ai-video-studio-dashboard.vercel.app),
# or a team/branch/per-PR preview (...-team-jarvy.vercel.app, per-PR previews
# get a random hash suffix, branch previews get "git-<branch>"). Matched by
# regex so a new preview URL works without an env var update on Railway for
# every deploy. Exact origins from DASHBOARD_CORS_ORIGINS are still required
# for anything outside Vercel.
_VERCEL_PREVIEW_ORIGIN_RE = (
    r"^https://ai-video-studio-dashboard"
    r"(\.vercel\.app|(-[a-z0-9-]+)?-team-jarvy\.vercel\.app)$"
)


def _cors_origins() -> list[str]:
    raw = os.getenv("DASHBOARD_CORS_ORIGINS")
    if not raw:
        return _DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Phase 1.1 P0 fix, Fix 9: on startup, reap any render scratch files
    (.part.<ext> / .stderr.log) orphaned by a hard process kill - see
    ProjectManager.reap_orphaned_render_artifacts's docstring for exactly
    what these files are and why they're always safe to remove. Runs before
    the app starts accepting requests; uses the same ProjectManager
    singleton the routes resolve to (get_project_manager's own docstring:
    it reads settings.OUTPUT_DIR fresh on every call), so this also does
    the right thing in tests where OUTPUT_DIR is monkeypatched per-test.

    On shutdown, releases PipelineExecutor's thread pool - not required for
    correctness (concurrent.futures registers its own atexit cleanup), but
    keeps a long-lived server from accumulating idle pool threads across
    an app's lifetime, and keeps test teardown tidy."""
    removed = get_project_manager().reap_orphaned_render_artifacts()
    if removed:
        logger.info(
            f"Startup reaper removed {len(removed)} orphaned render artifact(s): "
            f"{[str(p) for p in removed]}"
        )
    yield
    app.state.pipeline_executor.shutdown(wait=False)


def create_app() -> FastAPI:
    """App factory for the web API layer - a fifth thin client, parallel to
    app.py/producer_app.py/render_app.py/publish_app.py, calling the same
    ProjectManager the CLIs already use (WEB_DASHBOARD_ARCHITECTURE.md).
    Nothing in director_studio/, producer_studio/, execution_engine/,
    publishing_engine/, or the existing ProjectManager methods is touched.

    One RunRegistry per app instance, held on app.state rather than a
    process-wide singleton, so each app (including one built fresh per test
    via TestClient(create_app())) tracks its own in-flight runs. Same
    convention now applies to PipelineExecutor (Phase 1.1 P0 fix, see
    web_api/pipeline_executor.py) - one bounded, dedicated thread pool per
    app instance."""
    app = FastAPI(title="AI Video Studio API", version=API_VERSION, lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_VERCEL_PREVIEW_ORIGIN_RE,
        allow_methods=["*"],
        allow_headers=["*"],
        # Login/register/logout/session-restore (frontend/api/auth.ts) all
        # send credentials: "include" - required because /auth/login also
        # sets an HttpOnly session cookie, not just a bearer token in the
        # body. Per the Fetch/CORS spec, a credentialed cross-origin request
        # gets its response silently withheld from page JS (fetch() rejects
        # with "TypeError: Failed to fetch", before any application code -
        # status check, redirect, error banner - ever runs) unless the
        # server answers with Access-Control-Allow-Credentials: true. Without
        # this, login is broken in every real browser on every deployment
        # where the frontend and backend are different origins - which is
        # always true here (localhost:3000 vs 127.0.0.1:8000 in dev; the
        # real Vercel/Railway split in production). Safe to combine with a
        # non-wildcard allow_origins/allow_origin_regex (both already are);
        # CORSMiddleware then echoes the exact matched Origin rather than
        # "*", which credentialed responses require anyway.
        allow_credentials=True,
    )
    app.state.run_registry = RunRegistry()
    app.state.pipeline_executor = PipelineExecutor(
        max_workers=settings.PIPELINE_MAX_CONCURRENCY,
        run_timeout_seconds=settings.PIPELINE_TIMEOUT_SECONDS,
    )
    app.include_router(system.router)
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(producer.router)
    app.include_router(render.router)
    app.include_router(publish.router)
    app.include_router(runs.router)
    app.include_router(events.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(auth.router)
    return app

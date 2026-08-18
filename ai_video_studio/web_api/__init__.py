import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_api.routers import events, producer, projects, publish, render, runs, system
from web_api.routers.system import API_VERSION
from web_api.run_registry import RunRegistry

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


def create_app() -> FastAPI:
    """App factory for the web API layer - a fifth thin client, parallel to
    app.py/producer_app.py/render_app.py/publish_app.py, calling the same
    ProjectManager the CLIs already use (WEB_DASHBOARD_ARCHITECTURE.md).
    Nothing in director_studio/, producer_studio/, execution_engine/,
    publishing_engine/, or the existing ProjectManager methods is touched.

    One RunRegistry per app instance, held on app.state rather than a
    process-wide singleton, so each app (including one built fresh per test
    via TestClient(create_app())) tracks its own in-flight runs."""
    app = FastAPI(title="AI Video Studio API", version=API_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_VERCEL_PREVIEW_ORIGIN_RE,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.run_registry = RunRegistry()
    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(producer.router)
    app.include_router(render.router)
    app.include_router(publish.router)
    app.include_router(runs.router)
    app.include_router(events.router)
    return app

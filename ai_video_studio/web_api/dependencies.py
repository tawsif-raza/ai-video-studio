from functools import lru_cache
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from auth.security import ExpiredTokenError, InvalidTokenError, decode_access_token
from auth.user_store import LocalUserStore, UserStore
from config import settings
from director_studio.controller import DirectorStudioController
from execution_engine.controller import ExecutionEngineController
from llm.failover_client import FailoverLLMClient as LLMClient
from producer_studio.controller import ProducerStudioController
from project_manager.manager import ProjectManager
from publishing_engine.controller import PublishingEngineController
from shared_core.contracts.user import UserResponse
from web_api.run_registry import RunRegistry
from web_api.sse import DEFAULT_POLL_INTERVAL_SECONDS


@lru_cache
def get_project_manager() -> ProjectManager:
    """One ProjectManager instance per process, exactly like each CLI
    constructs exactly one (app.py, producer_app.py, render_app.py,
    publish_app.py). ProjectManager itself holds no per-request state - it
    reads settings.OUTPUT_DIR fresh on every call - so a single cached
    instance is safe to share across all requests and, in tests, across
    OUTPUT_DIR monkeypatches too."""
    return ProjectManager()


def get_run_registry(request: Request) -> RunRegistry:
    """Unlike get_project_manager, deliberately NOT a process-wide
    lru_cache singleton: the registry is created once per app instance in
    create_app() (web_api/__init__.py) and stored on app.state, so every
    TestClient(create_app()) in tests gets its own isolated registry
    instead of leaking Run objects across unrelated test cases."""
    return request.app.state.run_registry


def get_llm_client_factory():
    """Returns the same LLM client class app.py already uses
    (llm.failover_client.FailoverLLMClient) - a factory, not an instance, so
    each Director Studio run gets its own client the same way app.py's
    main() does. Overridden in tests via app.dependency_overrides to inject
    a fake LLM client without touching Director Studio."""
    return LLMClient


def get_director_controller_factory():
    """Returns the unmodified DirectorStudioController class. Overridden in
    tests that need to exercise the API boundary's SystemExit/exception
    handling deterministically, without depending on real agent/LLM
    behavior to produce a failure."""
    return DirectorStudioController


def get_producer_controller_factory():
    """Returns the unmodified ProducerStudioController class. Overridden in
    tests the same way get_director_controller_factory is."""
    return ProducerStudioController


def get_execution_controller_factory():
    """Returns the unmodified ExecutionEngineController class, called as
    controller_factory(project_manager) exactly like the other two
    factories - detector/executor/prober all default to the real
    ffmpeg-backed implementations (execution_engine/controller.py), never
    reimplemented here. Overridden in tests with a callable that injects
    fake detector/executor/prober (the same seam
    tests/integration/test_render_pipeline.py already uses) so render
    behavior can be exercised deterministically without a real ffmpeg
    binary."""
    return ExecutionEngineController


def get_publish_controller_factory():
    """Returns the unmodified PublishingEngineController class - called as
    controller_factory() with NO arguments (unlike the producer/execution
    factories), because PublishingEngineController.__init__ takes only
    keyword-only args that all default (platform_resolver, readiness_check,
    credential_provider, auth_cache) and never accepts a project_manager;
    it never imports project_manager at all (publishing_engine/controller.py's
    own docstring: "It still never imports project_manager"). Overridden in
    tests with a callable that injects fake platform_resolver/
    readiness_check/credential_provider/auth_cache, the same seam
    tests/test_publishing_controller.py already uses."""
    return PublishingEngineController


def get_sse_poll_interval() -> float:
    """How often web_api/sse.py's run_events() polls RunRegistry.get() for
    a status change. A plain float, not a class/instance - overridden in
    tests to a much smaller value so streaming tests don't have to wait
    out a production-scale interval to observe a transition."""
    return DEFAULT_POLL_INTERVAL_SECONDS


def get_user_store() -> UserStore:
    """Provides the active UserStore instance. Uses the singleton instance
    if one has been configured (or set via set_user_store), otherwise returns
    a LocalUserStore configured for the current settings.OUTPUT_DIR."""
    from auth.user_store import _user_store_instance
    if _user_store_instance is not None:
        return _user_store_instance
    return LocalUserStore(settings.OUTPUT_DIR / "users")


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    session_token: Optional[str] = Cookie(None, alias="session_token"),
    user_store: UserStore = Depends(get_user_store),
) -> UserResponse:
    """FastAPI dependency that extracts and validates the JWT bearer token
    from either the HTTP Authorization header or an HTTP-only cookie
    ('access_token' or 'session_token'). Returns the authenticated UserResponse
    model with sensitive fields (password hash and salt) stripped."""
    token: Optional[str] = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
    elif access_token:
        token = access_token
    elif session_token:
        token = session_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("scope") == "password_reset":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cannot use password reset token as an access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_store.get_by_id(user_id)
    if user is None:
        email = payload.get("email")
        if email:
            user = user_store.get_by_email(email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user.to_response()


def get_optional_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    access_token: Optional[str] = Cookie(None, alias="access_token"),
    session_token: Optional[str] = Cookie(None, alias="session_token"),
    user_store: UserStore = Depends(get_user_store),
) -> Optional[UserResponse]:
    """Dependency for endpoints that accept optional authentication."""
    if not authorization and not access_token and not session_token:
        return None
    try:
        return get_current_user(
            authorization=authorization,
            access_token=access_token,
            session_token=session_token,
            user_store=user_store,
        )
    except HTTPException:
        return None

"""Regression tests for the login-breaking CORS bug: a cross-origin request
made with `credentials: "include"` (frontend/api/auth.ts's login/register/
getMe/logout calls - required because /auth/login also sets an HttpOnly
session cookie, not just a bearer token) is only usable by a real browser
if the server answers with Access-Control-Allow-Credentials: true. Without
it, no application code (status check, redirect, error banner) ever runs -
the browser's fetch() rejects with "TypeError: Failed to fetch" before the
response is exposed to page JS at all. TestClient does not enforce this
browser-side blocking behavior itself, so these tests instead assert on the
one thing that actually determines whether a real browser would allow it:
the presence and value of Access-Control-Allow-Credentials on the response
CORSMiddleware produces for a credentialed cross-origin request."""
from fastapi.testclient import TestClient

from web_api import create_app

FRONTEND_ORIGIN = "http://localhost:3000"


def test_login_response_allows_credentialed_cross_origin_requests(tmp_path, monkeypatch):
    from auth.user_store import LocalUserStore, set_user_store
    from config import settings

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    set_user_store(LocalUserStore(tmp_path / "users"))
    client = TestClient(create_app())

    client.post(
        "/auth/register",
        json={"email": "cors_test@example.com", "full_name": "CORS Test", "password": "secret_password"},
        headers={"Origin": FRONTEND_ORIGIN},
    )

    response = client.post(
        "/auth/login",
        json={"email": "cors_test@example.com", "password": "secret_password"},
        headers={"Origin": FRONTEND_ORIGIN},
    )

    assert response.status_code == 200
    # The specific header whose absence breaks every credentialed browser
    # request - this is the exact regression this test exists to catch.
    assert response.headers.get("access-control-allow-credentials") == "true"
    # Per the CORS spec, this must be the exact origin (never "*") when
    # credentials are allowed - a wildcard would be rejected by the browser
    # just as thoroughly as a missing credentials header.
    assert response.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN

    set_user_store(None)


def test_login_preflight_allows_credentials():
    """A real browser sends an OPTIONS preflight before the actual
    credentialed POST for a request with a Content-Type header like
    application/json - this must also carry the credentials ack, or the
    browser never even attempts the real request."""
    client = TestClient(create_app())

    response = client.options(
        "/auth/login",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert response.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


def test_get_me_response_allows_credentialed_cross_origin_requests(tmp_path, monkeypatch):
    """getMe() (frontend/api/auth.ts) is what session-restore-after-refresh
    depends on, and it also uses credentials: "include" - must be covered
    by the same fix, not just /auth/login."""
    from auth.user_store import LocalUserStore, set_user_store
    from config import settings

    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    set_user_store(LocalUserStore(tmp_path / "users"))
    client = TestClient(create_app())

    register = client.post(
        "/auth/register",
        json={"email": "cors_me@example.com", "full_name": "CORS Me", "password": "secret_password"},
        headers={"Origin": FRONTEND_ORIGIN},
    )
    token = register.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Origin": FRONTEND_ORIGIN, "Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-credentials") == "true"

    set_user_store(None)


def test_cors_still_rejects_an_unconfigured_origin():
    """The fix must not weaken the existing origin allow-list - only a
    configured/matched origin should ever get an Allow-Origin echoed back,
    credentials or not."""
    client = TestClient(create_app())

    response = client.options(
        "/auth/login",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert "access-control-allow-origin" not in {k.lower() for k in response.headers.keys()}

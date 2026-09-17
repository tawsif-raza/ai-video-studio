"""Regression tests for the environment-driven session cookie
(Secure/SameSite) configuration - verifies the actual Set-Cookie header
FastAPI sends, in both a local-like and a production-like configuration,
rather than just the resolver/validator functions in isolation
(tests/test_config_cookies.py already covers those directly).

Monkeypatching config.settings.COOKIE_SECURE/COOKIE_SAMESITE is sufficient
without rebuilding the app: web_api/routers/auth.py's _set_session_cookie/
_clear_session_cookies read settings.COOKIE_SECURE/COOKIE_SAMESITE at
request time from the same singleton `settings` object these tests import
and patch."""

import pytest
from fastapi.testclient import TestClient

from auth.user_store import LocalUserStore, set_user_store
from config import settings
from web_api import create_app


@pytest.fixture
def cookie_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    set_user_store(LocalUserStore(tmp_path / "users"))
    app = create_app()
    yield TestClient(app)
    set_user_store(None)


def _register(client, email="cookie-test@example.com"):
    return client.post(
        "/auth/register",
        json={"email": email, "full_name": "Cookie Tester", "password": "password123"},
    )


def test_local_config_sets_insecure_lax_cookie(cookie_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")

    response = _register(cookie_client, "local-cookie@example.com")
    assert response.status_code == 201

    set_cookie_headers = response.headers.get_list("set-cookie")
    access_token_cookie = next(h for h in set_cookie_headers if h.startswith("access_token="))

    assert "samesite=lax" in access_token_cookie.lower()
    assert "secure" not in access_token_cookie.lower()
    assert "httponly" in access_token_cookie.lower()


def test_production_config_sets_secure_none_cookie(cookie_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")

    response = _register(cookie_client, "prod-cookie@example.com")
    assert response.status_code == 201

    set_cookie_headers = response.headers.get_list("set-cookie")
    access_token_cookie = next(h for h in set_cookie_headers if h.startswith("access_token="))

    assert "samesite=none" in access_token_cookie.lower()
    assert "secure" in access_token_cookie.lower()
    assert "httponly" in access_token_cookie.lower()


def test_login_cookie_matches_configured_environment(cookie_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")
    _register(cookie_client, "login-cookie@example.com")

    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")
    response = cookie_client.post(
        "/auth/login", json={"email": "login-cookie@example.com", "password": "password123"}
    )
    assert response.status_code == 200

    access_token_cookie = next(h for h in response.headers.get_list("set-cookie") if h.startswith("access_token="))
    assert "samesite=none" in access_token_cookie.lower()
    assert "secure" in access_token_cookie.lower()


def test_logout_clears_cookie_with_matching_attributes_local(cookie_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "lax")
    _register(cookie_client, "logout-local@example.com")

    response = cookie_client.post("/auth/logout")
    assert response.status_code == 200

    cleared = response.headers.get_list("set-cookie")
    access_cleared = next(h for h in cleared if h.startswith("access_token="))
    session_cleared = next(h for h in cleared if h.startswith("session_token="))
    for cookie_header in (access_cleared, session_cleared):
        assert "samesite=lax" in cookie_header.lower()
        assert "secure" not in cookie_header.lower()
        assert "max-age=0" in cookie_header.lower()


def test_logout_clears_cookie_with_matching_attributes_production(cookie_client, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")
    _register(cookie_client, "logout-prod@example.com")

    response = cookie_client.post("/auth/logout")
    assert response.status_code == 200

    cleared = response.headers.get_list("set-cookie")
    access_cleared = next(h for h in cleared if h.startswith("access_token="))
    session_cleared = next(h for h in cleared if h.startswith("session_token="))
    for cookie_header in (access_cleared, session_cleared):
        assert "samesite=none" in cookie_header.lower()
        assert "secure" in cookie_header.lower()
        assert "max-age=0" in cookie_header.lower()


def test_authorization_header_flow_is_unaffected_by_cookie_config(cookie_client, monkeypatch):
    """The bearer-token (Authorization header) flow the frontend actually
    relies on for every non-auth request must keep working identically
    regardless of the cookie configuration - this change only touches how
    the cookie is set, never the JWT/bearer mechanism itself."""
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    monkeypatch.setattr(settings, "COOKIE_SAMESITE", "none")

    register_resp = _register(cookie_client, "bearer-flow@example.com")
    token = register_resp.json()["access_token"]

    me_resp = cookie_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "bearer-flow@example.com"

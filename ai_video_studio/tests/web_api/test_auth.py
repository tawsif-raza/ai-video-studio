from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from auth.security import create_access_token, create_password_reset_token
from auth.user_store import LocalUserStore, set_user_store
from config import settings
from web_api import create_app


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """TestClient configured with an isolated temporary user directory."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    # Reset any process-wide user store instance so it binds to tmp_path
    set_user_store(LocalUserStore(tmp_path / "users"))
    app = create_app()
    yield TestClient(app)
    set_user_store(None)


def test_register_success(auth_client):
    payload = {
        "email": "creator@example.com",
        "full_name": "Creative Director",
        "password": "strongpassword123",
    }
    response = auth_client.post("/api/auth/register", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data

    user = data["user"]
    assert user["email"] == "creator@example.com"
    assert user["full_name"] == "Creative Director"
    assert user["is_active"] is True
    assert "id" in user
    assert "created_at" in user
    assert "hashed_password" not in user
    assert "salt" not in user

    # Verify cookie was set
    assert "access_token" in response.cookies


def test_register_alias_without_api_prefix(auth_client):
    payload = {
        "email": "direct@example.com",
        "full_name": "Direct Route User",
        "password": "strongpassword123",
    }
    response = auth_client.post("/auth/register", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "direct@example.com"


def test_register_duplicate_email_conflict(auth_client):
    payload = {
        "email": "duplicate@example.com",
        "full_name": "Original User",
        "password": "password123",
    }
    first = auth_client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    # Attempt to register again with same email
    second = auth_client.post("/api/auth/register", json=payload)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"].lower()

    # Attempt with uppercase variant of email
    variant_payload = {
        "email": "DUPLICATE@example.com",
        "full_name": "Another User",
        "password": "password123",
    }
    third = auth_client.post("/api/auth/register", json=variant_payload)
    assert third.status_code == 409


def test_register_validation_errors(auth_client):
    # Invalid email format
    res1 = auth_client.post("/api/auth/register", json={
        "email": "notanemail",
        "full_name": "Test",
        "password": "password123",
    })
    assert res1.status_code == 422

    # Empty full_name
    res2 = auth_client.post("/api/auth/register", json={
        "email": "valid@example.com",
        "full_name": "   ",
        "password": "password123",
    })
    assert res2.status_code == 422

    # Password too short (< 6 chars)
    res3 = auth_client.post("/api/auth/register", json={
        "email": "valid@example.com",
        "full_name": "Test",
        "password": "123",
    })
    assert res3.status_code == 422


def test_login_success(auth_client):
    # Register first
    auth_client.post("/api/auth/register", json={
        "email": "login_test@example.com",
        "full_name": "Login User",
        "password": "secret_password",
    })

    # Log in
    login_res = auth_client.post("/api/auth/login", json={
        "email": "login_test@example.com",
        "password": "secret_password",
    })

    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "login_test@example.com"
    assert "access_token" in login_res.cookies


def test_login_case_insensitive_email(auth_client):
    auth_client.post("/api/auth/register", json={
        "email": "caps_test@example.com",
        "full_name": "Caps User",
        "password": "secret_password",
    })

    login_res = auth_client.post("/api/auth/login", json={
        "email": "CAPS_TEST@EXAMPLE.COM",
        "password": "secret_password",
    })
    assert login_res.status_code == 200


def test_login_invalid_password(auth_client):
    auth_client.post("/api/auth/register", json={
        "email": "wrong_pw@example.com",
        "full_name": "User",
        "password": "correct_password",
    })

    response = auth_client.post("/api/auth/login", json={
        "email": "wrong_pw@example.com",
        "password": "wrong_password",
    })
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()
    assert response.headers.get("www-authenticate") == "Bearer"


def test_login_nonexistent_user(auth_client):
    response = auth_client.post("/api/auth/login", json={
        "email": "does_not_exist@example.com",
        "password": "anypassword",
    })
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


def test_get_me_with_bearer_token(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "me_bearer@example.com",
        "full_name": "Bearer Profile",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me_bearer@example.com"
    assert data["full_name"] == "Bearer Profile"
    assert "hashed_password" not in data

    # Route without /api prefix
    res_direct = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_direct.status_code == 200


def test_get_me_with_cookie(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "me_cookie@example.com",
        "full_name": "Cookie Profile",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    # Explicitly pass cookie without Authorization header
    response = auth_client.get(
        "/api/auth/me",
        cookies={"access_token": token},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me_cookie@example.com"

    # Also test session_token cookie alias
    response_session = auth_client.get(
        "/api/auth/me",
        cookies={"session_token": token},
    )
    assert response_session.status_code == 200
    assert response_session.json()["email"] == "me_cookie@example.com"


def test_get_me_unauthenticated(auth_client):
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401
    assert "not authenticated" in response.json()["detail"].lower()


def test_get_me_invalid_token(auth_client):
    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert response.status_code == 401
    assert "invalid authentication token" in response.json()["detail"].lower()


def test_get_me_expired_token(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "me_expired@example.com",
        "full_name": "Expired Profile",
        "password": "password123",
    })
    user_id = reg.json()["user"]["id"]

    # Issue an already expired token
    expired_token = create_access_token(
        data={"sub": user_id, "email": "me_expired@example.com"},
        expires_delta=timedelta(seconds=-30),
    )

    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_get_me_inactive_user(auth_client, tmp_path):
    reg = auth_client.post("/api/auth/register", json={
        "email": "inactive@example.com",
        "full_name": "Inactive User",
        "password": "password123",
    })
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Manually deactivate user in store
    store = LocalUserStore(tmp_path / "users")
    user_in_db = store.get_by_id(user_id)
    assert user_in_db is not None
    deactivated = user_in_db.model_copy(update={"is_active": False})
    store.update_user(deactivated)

    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


def test_get_me_user_deleted_from_store(auth_client, tmp_path):
    reg = auth_client.post("/api/auth/register", json={
        "email": "deleted@example.com",
        "full_name": "Deleted User",
        "password": "password123",
    })
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Delete user from store
    store = LocalUserStore(tmp_path / "users")
    store.delete_user(user_id)

    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "user not found" in response.json()["detail"].lower()


def test_update_me_updates_full_name(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "update_name@example.com",
        "full_name": "Original Name",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me",
        json={"full_name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "New Name"
    assert data["email"] == "update_name@example.com"

    # Persisted, not just returned in the response.
    reloaded = auth_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert reloaded.json()["full_name"] == "New Name"


def test_update_me_updates_preferences(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "update_prefs@example.com",
        "full_name": "Prefs User",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me",
        json={"preferences": {"dark_mode": "true", "aspect_ratio": "16:9"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["preferences"] == {"dark_mode": "true", "aspect_ratio": "16:9"}


def test_update_me_updates_api_keys(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "update_keys@example.com",
        "full_name": "Keys User",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me",
        json={"api_keys": {"gemini": "user-provided-key"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["api_keys"] == {"gemini": "user-provided-key"}


def test_update_me_partial_update_leaves_other_fields_untouched(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "partial_update@example.com",
        "full_name": "Partial User",
        "password": "password123",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    auth_client.patch("/api/auth/me", json={"preferences": {"dark_mode": "true"}}, headers=headers)
    response = auth_client.patch("/api/auth/me", json={"full_name": "Renamed"}, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Renamed"
    # PATCH semantics (exclude_unset): a field omitted from this second
    # request must not be wiped out by the first request's own update.
    assert data["preferences"] == {"dark_mode": "true"}


def test_update_me_empty_body_returns_current_user_unchanged(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "empty_update@example.com",
        "full_name": "Empty Body User",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me", json={}, headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Empty Body User"


def test_update_me_rejects_blank_full_name(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "blank_name@example.com",
        "full_name": "Has A Name",
        "password": "password123",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me",
        json={"full_name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_update_me_unauthenticated(auth_client):
    response = auth_client.patch("/api/auth/me", json={"full_name": "Nobody"})
    assert response.status_code == 401


def test_update_me_user_deleted_from_store(auth_client, tmp_path):
    reg = auth_client.post("/api/auth/register", json={
        "email": "update_deleted@example.com",
        "full_name": "Soon Deleted",
        "password": "password123",
    })
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    store = LocalUserStore(tmp_path / "users")
    store.delete_user(user_id)

    response = auth_client.patch(
        "/api/auth/me",
        json={"full_name": "Ghost"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # get_current_user's own lookup already 401s before update_me's route
    # body ever runs - same as test_get_me_user_deleted_from_store.
    assert response.status_code == 401


def test_update_password_success(auth_client):
    auth_client.post("/api/auth/register", json={
        "email": "change_pw@example.com",
        "full_name": "Password Changer",
        "password": "originalpassword",
    })
    login = auth_client.post("/api/auth/login", json={
        "email": "change_pw@example.com",
        "password": "originalpassword",
    })
    token = login.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me/password",
        json={"current_password": "originalpassword", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    old_login = auth_client.post("/api/auth/login", json={
        "email": "change_pw@example.com",
        "password": "originalpassword",
    })
    assert old_login.status_code == 401

    new_login = auth_client.post("/api/auth/login", json={
        "email": "change_pw@example.com",
        "password": "newpassword456",
    })
    assert new_login.status_code == 200


def test_update_password_wrong_current_password(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "wrong_current@example.com",
        "full_name": "User",
        "password": "correctpassword",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me/password",
        json={"current_password": "wrongpassword", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "incorrect" in response.json()["detail"].lower()

    # Nothing was changed - the original password still works.
    still_works = auth_client.post("/api/auth/login", json={
        "email": "wrong_current@example.com",
        "password": "correctpassword",
    })
    assert still_works.status_code == 200


def test_update_password_rejects_short_new_password(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "short_pw@example.com",
        "full_name": "User",
        "password": "correctpassword",
    })
    token = reg.json()["access_token"]

    response = auth_client.patch(
        "/api/auth/me/password",
        json={"current_password": "correctpassword", "new_password": "abc"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_update_password_unauthenticated(auth_client):
    response = auth_client.patch(
        "/api/auth/me/password",
        json={"current_password": "x", "new_password": "abcdef"},
    )
    assert response.status_code == 401


def test_update_password_user_deleted_from_store(auth_client, tmp_path):
    reg = auth_client.post("/api/auth/register", json={
        "email": "pw_deleted@example.com",
        "full_name": "Soon Deleted",
        "password": "originalpassword",
    })
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    store = LocalUserStore(tmp_path / "users")
    store.delete_user(user_id)

    response = auth_client.patch(
        "/api/auth/me/password",
        json={"current_password": "originalpassword", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_logout(auth_client):
    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "logged out" in data["message"].lower()

    # Route without /api prefix
    res_direct = auth_client.post("/auth/logout")
    assert res_direct.status_code == 200


def test_forgot_password_success(auth_client):
    auth_client.post("/api/auth/register", json={
        "email": "reset_user@example.com",
        "full_name": "Reset User",
        "password": "oldpassword123",
    })

    response = auth_client.post("/api/auth/forgot-password", json={
        "email": "reset_user@example.com",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "password reset link has been sent" in data["message"].lower()
    # In dev/test mode, reset_token should be included
    assert data["reset_token"] is not None

    # Test route without /api prefix
    res_direct = auth_client.post("/auth/forgot-password", json={
        "email": "reset_user@example.com",
    })
    assert res_direct.status_code == 200


def test_forgot_password_nonexistent_email_neutral(auth_client):
    response = auth_client.post("/api/auth/forgot-password", json={
        "email": "nobody@example.com",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "password reset link has been sent" in data["message"].lower()
    # Neutral response prevents enumeration: no token returned
    assert data["reset_token"] is None


def test_forgot_password_invalid_email(auth_client):
    response = auth_client.post("/api/auth/forgot-password", json={
        "email": "not-an-email",
    })
    assert response.status_code == 422


def test_reset_password_success(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "changeme@example.com",
        "full_name": "Change Me",
        "password": "initialpassword123",
    })
    assert reg.status_code == 201

    # Request reset token
    forgot_res = auth_client.post("/api/auth/forgot-password", json={
        "email": "changeme@example.com",
    })
    token = forgot_res.json()["reset_token"]
    assert token is not None

    # Reset password
    reset_res = auth_client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "brandnewpassword456",
    })
    assert reset_res.status_code == 200
    data = reset_res.json()
    assert data["status"] == "ok"
    assert "successfully reset" in data["message"].lower()

    # Login with old password fails
    old_login = auth_client.post("/api/auth/login", json={
        "email": "changeme@example.com",
        "password": "initialpassword123",
    })
    assert old_login.status_code == 401

    # Login with new password succeeds
    new_login = auth_client.post("/api/auth/login", json={
        "email": "changeme@example.com",
        "password": "brandnewpassword456",
    })
    assert new_login.status_code == 200
    assert new_login.json()["user"]["email"] == "changeme@example.com"


def test_reset_password_single_use_token(auth_client):
    auth_client.post("/api/auth/register", json={
        "email": "singleuse@example.com",
        "full_name": "Single Use",
        "password": "password123",
    })

    forgot_res = auth_client.post("/api/auth/forgot-password", json={
        "email": "singleuse@example.com",
    })
    token = forgot_res.json()["reset_token"]

    # First reset succeeds
    first_res = auth_client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "firstnewpassword",
    })
    assert first_res.status_code == 200

    # Second reset with identical token MUST fail
    second_res = auth_client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "secondnewpassword",
    })
    assert second_res.status_code == 400
    assert "already been used or invalidated" in second_res.json()["detail"].lower()


def test_reset_password_expired_token(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "expired_reset@example.com",
        "full_name": "Expired Reset",
        "password": "password123",
    })
    user_id = reg.json()["user"]["id"]

    expired_token = create_password_reset_token(
        user_id=user_id,
        email="expired_reset@example.com",
        expires_delta=timedelta(seconds=-30),
    )

    response = auth_client.post("/api/auth/reset-password", json={
        "token": expired_token,
        "new_password": "newpassword123",
    })
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_reset_password_invalid_or_tampered_token(auth_client):
    response = auth_client.post("/api/auth/reset-password", json={
        "token": "gibberish.token.value",
        "new_password": "newpassword123",
    })
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_reset_password_validation_error(auth_client):
    response = auth_client.post("/api/auth/reset-password", json={
        "token": "anytoken",
        "new_password": "short",
    })
    assert response.status_code == 422


def test_reset_password_inactive_user(auth_client, tmp_path):
    reg = auth_client.post("/api/auth/register", json={
        "email": "inactive_reset@example.com",
        "full_name": "Inactive Reset",
        "password": "password123",
    })
    token = auth_client.post("/api/auth/forgot-password", json={
        "email": "inactive_reset@example.com",
    }).json()["reset_token"]
    user_id = reg.json()["user"]["id"]

    # Deactivate user
    store = LocalUserStore(tmp_path / "users")
    user = store.get_by_id(user_id)
    store.update_user(user.model_copy(update={"is_active": False}))

    response = auth_client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "newpassword123",
    })
    assert response.status_code == 403
    assert "inactive" in response.json()["detail"].lower()


def test_cannot_use_access_token_as_reset_token(auth_client):
    reg = auth_client.post("/api/auth/register", json={
        "email": "accesstokenuser@example.com",
        "full_name": "Access User",
        "password": "password123",
    })
    access_token = reg.json()["access_token"]

    response = auth_client.post("/api/auth/reset-password", json={
        "token": access_token,
        "new_password": "newpassword123",
    })
    assert response.status_code == 400
    assert "not valid for password reset" in response.json()["detail"].lower()


def test_cannot_use_reset_token_as_access_token(auth_client):
    auth_client.post("/api/auth/register", json={
        "email": "reset_to_access@example.com",
        "full_name": "Reset Access",
        "password": "password123",
    })
    forgot_res = auth_client.post("/api/auth/forgot-password", json={
        "email": "reset_to_access@example.com",
    })
    reset_token = forgot_res.json()["reset_token"]

    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {reset_token}"},
    )
    assert response.status_code == 401
    assert "cannot use password reset token as an access token" in response.json()["detail"].lower()


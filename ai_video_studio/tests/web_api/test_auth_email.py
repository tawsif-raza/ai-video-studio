"""Regression tests for the SES-backed forgot-password email wiring
(web_api/routers/auth.py's forgot_password + auth/email.py). Verifies:
  - the email send is triggered exactly when SES is configured and the
    account exists
  - a delivery failure never changes the (enumeration-safe) HTTP response
  - reset_token is never present in the response body in production,
    regardless of whether SES is configured or the send succeeded
  - no reset token/link ever reaches the application logger
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from auth import email as reset_email
from auth.user_store import LocalUserStore, set_user_store
from config import settings
from web_api import create_app


@pytest.fixture
def email_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "")
    monkeypatch.setattr(settings, "SES_REGION", "")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    set_user_store(LocalUserStore(tmp_path / "users"))
    app = create_app()
    yield TestClient(app)
    set_user_store(None)


def _register(client, email_addr="reset-me@example.com"):
    return client.post(
        "/auth/register",
        json={"email": email_addr, "full_name": "Reset Me", "password": "password123"},
    )


def test_forgot_password_sends_email_when_ses_configured(email_client, monkeypatch):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    _register(email_client, "ses-user@example.com")

    fake_client = MagicMock()
    monkeypatch.setattr(reset_email.boto3, "client", MagicMock(return_value=fake_client))

    response = email_client.post("/auth/forgot-password", json={"email": "ses-user@example.com"})

    assert response.status_code == 200
    fake_client.send_email.assert_called_once()
    call_kwargs = fake_client.send_email.call_args.kwargs
    assert call_kwargs["Destination"] == {"ToAddresses": ["ses-user@example.com"]}


def test_forgot_password_does_not_send_email_when_ses_not_configured(email_client, monkeypatch):
    _register(email_client, "no-ses-user@example.com")

    fake_boto3_client = MagicMock()
    monkeypatch.setattr(reset_email.boto3, "client", fake_boto3_client)

    response = email_client.post("/auth/forgot-password", json={"email": "no-ses-user@example.com"})

    assert response.status_code == 200
    fake_boto3_client.assert_not_called()


def test_forgot_password_does_not_send_email_for_nonexistent_account(email_client, monkeypatch):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")

    fake_boto3_client = MagicMock()
    monkeypatch.setattr(reset_email.boto3, "client", fake_boto3_client)

    response = email_client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert response.status_code == 200
    fake_boto3_client.assert_not_called()


def test_forgot_password_response_stays_neutral_when_email_delivery_fails(email_client, monkeypatch):
    """A delivery failure must not surface to the caller as anything other
    than the same neutral response an existing/nonexistent account and a
    successful send all produce - otherwise the response itself becomes an
    account-enumeration or SES-health oracle."""
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    _register(email_client, "failing-send@example.com")

    fake_client = MagicMock()
    fake_client.send_email.side_effect = reset_email.EmailDeliveryError("boom")
    monkeypatch.setattr(reset_email.boto3, "client", MagicMock(return_value=fake_client))

    ok_response = email_client.post("/auth/forgot-password", json={"email": "failing-send@example.com"})
    baseline_response = email_client.post("/auth/forgot-password", json={"email": "nonexistent@example.com"})

    assert ok_response.status_code == baseline_response.status_code == 200
    assert ok_response.json()["status"] == baseline_response.json()["status"] == "ok"
    assert ok_response.json()["message"] == baseline_response.json()["message"]


def test_reset_token_never_in_response_body_in_production_even_with_ses_configured(email_client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    monkeypatch.delenv("AUTH_DEV_MODE", raising=False)
    _register(email_client, "prod-user@example.com")

    fake_client = MagicMock()
    monkeypatch.setattr(reset_email.boto3, "client", MagicMock(return_value=fake_client))

    response = email_client.post("/auth/forgot-password", json={"email": "prod-user@example.com"})

    assert response.status_code == 200
    assert response.json()["reset_token"] is None


def test_no_reset_link_or_token_reaches_the_logger(email_client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://studio.example.com")
    _register(email_client, "logging-check@example.com")

    fake_client = MagicMock()
    monkeypatch.setattr(reset_email.boto3, "client", MagicMock(return_value=fake_client))

    with caplog.at_level("DEBUG"):
        response = email_client.post("/auth/forgot-password", json={"email": "logging-check@example.com"})

    reset_token = response.json()["reset_token"]
    assert reset_token  # sanity: dev mode did return one, so there's something real to check for

    for record in caplog.records:
        message = record.getMessage()
        assert reset_token not in message
        assert "reset-password?token=" not in message

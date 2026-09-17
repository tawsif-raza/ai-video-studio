from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from auth import email
from config import settings


@pytest.fixture(autouse=True)
def _reset_ses_settings(monkeypatch):
    """Every test in this file controls its own SES_FROM_EMAIL/SES_REGION/
    FRONTEND_BASE_URL explicitly rather than inheriting whatever the real
    process environment happens to have - keeps these tests deterministic
    regardless of what's configured on the machine running them."""
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "")
    monkeypatch.setattr(settings, "SES_REGION", "")
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "")


def test_is_configured_false_when_ses_from_email_blank():
    assert email.is_configured() is False


def test_is_configured_true_when_ses_from_email_set(monkeypatch):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    assert email.is_configured() is True


def test_build_reset_link_relative_when_frontend_base_url_unset():
    link = email.build_reset_link("abc123")
    assert link == "/reset-password?token=abc123"


def test_build_reset_link_absolute_when_frontend_base_url_set(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://studio.example.com")
    link = email.build_reset_link("abc123")
    assert link == "https://studio.example.com/reset-password?token=abc123"


def test_build_reset_link_url_encodes_token(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://studio.example.com")
    link = email.build_reset_link("token/with+special chars")
    assert "token%2Fwith%2Bspecial%20chars" in link


def test_send_password_reset_email_is_a_noop_when_not_configured(monkeypatch):
    fake_boto3_client = MagicMock()
    monkeypatch.setattr(email.boto3, "client", fake_boto3_client)

    email.send_password_reset_email("user@example.com", "https://studio.example.com/reset-password?token=x")

    fake_boto3_client.assert_not_called()


def test_send_password_reset_email_calls_ses_send_email(monkeypatch):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setattr(settings, "SES_REGION", "ap-south-1")

    fake_client = MagicMock()
    monkeypatch.setattr(email.boto3, "client", MagicMock(return_value=fake_client))

    email.send_password_reset_email("user@example.com", "https://studio.example.com/reset-password?token=x")

    email.boto3.client.assert_called_once_with("ses", region_name="ap-south-1")
    fake_client.send_email.assert_called_once()
    call_kwargs = fake_client.send_email.call_args.kwargs
    assert call_kwargs["Source"] == "noreply@example.com"
    assert call_kwargs["Destination"] == {"ToAddresses": ["user@example.com"]}
    assert "https://studio.example.com/reset-password?token=x" in call_kwargs["Message"]["Body"]["Text"]["Data"]


def test_send_password_reset_email_raises_email_delivery_error_on_client_error(monkeypatch):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")

    fake_client = MagicMock()
    fake_client.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}}, "SendEmail"
    )
    monkeypatch.setattr(email.boto3, "client", MagicMock(return_value=fake_client))

    with pytest.raises(email.EmailDeliveryError):
        email.send_password_reset_email("user@example.com", "https://studio.example.com/reset-password?token=x")


def test_send_password_reset_email_never_logs_the_reset_link(monkeypatch, caplog):
    """Do not expose reset tokens/links in logs (any environment) -
    verifies the actual log records emitted by a real send, not just the
    function's return value."""
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    fake_client = MagicMock()
    monkeypatch.setattr(email.boto3, "client", MagicMock(return_value=fake_client))

    secret_link = "https://studio.example.com/reset-password?token=super-secret-token-value"
    with caplog.at_level("DEBUG"):
        email.send_password_reset_email("user@example.com", secret_link)

    for record in caplog.records:
        assert "super-secret-token-value" not in record.getMessage()
        assert secret_link not in record.getMessage()


def test_failed_send_never_logs_the_reset_link_either(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SES_FROM_EMAIL", "noreply@example.com")
    fake_client = MagicMock()
    fake_client.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address not verified"}}, "SendEmail"
    )
    monkeypatch.setattr(email.boto3, "client", MagicMock(return_value=fake_client))

    secret_link = "https://studio.example.com/reset-password?token=super-secret-token-value"
    with caplog.at_level("DEBUG"):
        with pytest.raises(email.EmailDeliveryError):
            email.send_password_reset_email("user@example.com", secret_link)

    for record in caplog.records:
        assert "super-secret-token-value" not in record.getMessage()
        assert secret_link not in record.getMessage()

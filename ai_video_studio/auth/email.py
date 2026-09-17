from urllib.parse import quote

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import settings
from utils.logger import get_logger

logger = get_logger("auth.email")


class EmailDeliveryError(Exception):
    """Raised when SES rejects or fails a password-reset send. Callers
    should catch this and keep the API's neutral forgot-password response
    unchanged (see web_api/routers/auth.py) - a delivery failure must not
    turn into an account-enumeration signal or a 500."""


def is_configured() -> bool:
    """SES_FROM_EMAIL unset means "no email delivery configured" - the
    same optional-prerequisite convention config.py uses for S3_BUCKET_NAME/
    DB_HOST/SQS_QUEUE_URL. Local dev leaves this unset and keeps using the
    existing dev-mode reset_token response field instead."""
    return bool(settings.SES_FROM_EMAIL)


def build_reset_link(token: str) -> str:
    """Absolute link when FRONTEND_BASE_URL is configured (required for a
    real email - a mail client has no origin to resolve a relative path
    against); falls back to a relative path if it isn't, so nothing breaks
    for a deployment that hasn't set it yet."""
    path = f"/reset-password?token={quote(token, safe='')}"
    return f"{settings.FRONTEND_BASE_URL}{path}" if settings.FRONTEND_BASE_URL else path


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """Sends the password-reset email via Amazon SES.

    Credentials come entirely from boto3's default credential chain - the
    ECS task role in a deployed environment, or whatever AWS CLI/SSO
    session is active when run locally. No access key ID/secret is read,
    constructed, or accepted by this function or anywhere in config.py.

    No-ops if SES isn't configured (see is_configured) so this is always
    safe to call from forgot_password regardless of environment.

    Never logs the reset link or token, in any environment - only that a
    send to a given recipient was attempted/succeeded/failed, matching the
    same recipient-only logging forgot_password already does for token
    generation.
    """
    if not is_configured():
        return

    client = boto3.client("ses", region_name=settings.SES_REGION or None)
    subject = "Reset your AI Video Studio password"
    body_text = (
        "We received a request to reset your AI Video Studio password.\n\n"
        f"Reset your password by opening this link: {reset_link}\n\n"
        "This link expires in 1 hour and can only be used once. If you did "
        "not request a password reset, you can safely ignore this email."
    )

    try:
        client.send_email(
            Source=settings.SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "utf-8"},
                "Body": {"Text": {"Data": body_text, "Charset": "utf-8"}},
            },
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error(f"Failed to send password reset email to {to_email}: {type(exc).__name__}: {exc}")
        raise EmailDeliveryError(str(exc)) from exc

    logger.info(f"Password reset email sent to {to_email}")

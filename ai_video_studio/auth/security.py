import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import jwt

DEFAULT_ITERATIONS = 100_000
DEFAULT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
DEFAULT_RESET_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
DEFAULT_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "ai-video-studio-auth-secret-key-change-in-production-min32chars")


class SecurityError(Exception):
    """Base exception for security and authentication routines."""
    pass


class InvalidTokenError(SecurityError):
    """Raised when an authentication token is malformed or signature fails."""
    pass


class ExpiredTokenError(SecurityError):
    """Raised when an authentication token has passed its expiration time."""
    pass


def generate_salt(num_bytes: int = 16) -> str:
    """
    Generate a cryptographically secure random hexadecimal salt.
    """
    return secrets.token_hex(num_bytes)


def hash_password(password: str, salt: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256 with salt.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    if not salt:
        raise ValueError("Salt cannot be empty")
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations=iterations,
    )
    return dk.hex()


def create_password_hash(
    password: str,
    salt: Optional[str] = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> Tuple[str, str]:
    """
    Generate a new salt (if not provided) and return (hashed_password, salt).
    """
    actual_salt = salt if salt is not None else generate_salt()
    return hash_password(password, actual_salt, iterations=iterations), actual_salt


def verify_password(
    plain_password: str,
    hashed_password: str,
    salt: str,
    iterations: int = DEFAULT_ITERATIONS,
) -> bool:
    """
    Verify a plaintext password against a stored hash and salt in constant time.
    """
    if not plain_password or not hashed_password or not salt:
        return False
    try:
        computed_hash = hash_password(plain_password, salt, iterations=iterations)
        return hmac.compare_digest(computed_hash, hashed_password)
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
    algorithm: str = DEFAULT_ALGORITHM,
) -> str:
    """
    Create a signed JWT access token containing arbitrary payload claims.
    """
    to_encode = data.copy()
    now = datetime.now(UTC)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)))

    to_encode.update({
        "exp": expire,
        "iat": now,
    })
    key = secret_key or os.getenv("AUTH_SECRET_KEY", DEFAULT_SECRET_KEY)
    return jwt.encode(to_encode, key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: Optional[str] = None,
    algorithm: str = DEFAULT_ALGORITHM,
) -> Dict[str, Any]:
    """
    Decode and verify a signed JWT access token.
    Raises ExpiredTokenError or InvalidTokenError if verification fails.
    """
    key = secret_key or os.getenv("AUTH_SECRET_KEY", DEFAULT_SECRET_KEY)
    try:
        payload = jwt.decode(token, key, algorithms=[algorithm])
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("Authentication token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"Invalid authentication token: {exc}") from exc


def create_password_reset_token(
    user_id: str,
    email: str,
    password_fingerprint: str = "",
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
    algorithm: str = DEFAULT_ALGORITHM,
) -> str:
    """
    Create a signed JWT token specifically for password recovery.
    Claims include sub (user_id), email, scope='password_reset', and optional pwd_fp.
    """
    now = datetime.now(UTC)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(
            minutes=int(os.getenv("RESET_TOKEN_EXPIRE_MINUTES", DEFAULT_RESET_TOKEN_EXPIRE_MINUTES))
        )

    payload = {
        "sub": user_id,
        "email": email.strip().lower(),
        "scope": "password_reset",
        "pwd_fp": password_fingerprint,
        "iat": now,
        "exp": expire,
    }
    key = secret_key or os.getenv("AUTH_SECRET_KEY", DEFAULT_SECRET_KEY)
    return jwt.encode(payload, key, algorithm=algorithm)


def decode_password_reset_token(
    token: str,
    secret_key: Optional[str] = None,
    algorithm: str = DEFAULT_ALGORITHM,
) -> Dict[str, Any]:
    """
    Decode and verify a password reset token.
    Raises InvalidTokenError or ExpiredTokenError if verification fails or scope != 'password_reset'.
    """
    payload = decode_access_token(token, secret_key=secret_key, algorithm=algorithm)
    if payload.get("scope") != "password_reset":
        raise InvalidTokenError("Token is not valid for password reset")
    if not payload.get("sub") or not payload.get("email"):
        raise InvalidTokenError("Reset token missing required subject or email claims")
    return payload

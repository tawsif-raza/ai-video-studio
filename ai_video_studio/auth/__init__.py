"""
Authentication and identity module for AI Video Studio.
Provides cryptographic routines, user contracts, and persistent user store.
"""

from auth.security import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_ALGORITHM,
    DEFAULT_ITERATIONS,
    ExpiredTokenError,
    InvalidTokenError,
    SecurityError,
    create_access_token,
    create_password_hash,
    decode_access_token,
    generate_salt,
    hash_password,
    verify_password,
)
from auth.user_store import (
    LocalUserStore,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserStore,
    get_user_store,
    set_user_store,
)

__all__ = [
    "DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES",
    "DEFAULT_ALGORITHM",
    "DEFAULT_ITERATIONS",
    "ExpiredTokenError",
    "InvalidTokenError",
    "SecurityError",
    "create_access_token",
    "create_password_hash",
    "decode_access_token",
    "generate_salt",
    "hash_password",
    "verify_password",
    "UserStore",
    "LocalUserStore",
    "UserAlreadyExistsError",
    "UserNotFoundError",
    "get_user_store",
    "set_user_store",
]

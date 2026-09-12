from datetime import timedelta
import pytest

from auth.security import (
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    create_password_hash,
    decode_access_token,
    generate_salt,
    hash_password,
    verify_password,
)


def test_salt_generation_uniqueness_and_format():
    salt1 = generate_salt(16)
    salt2 = generate_salt(16)

    assert isinstance(salt1, str)
    assert isinstance(salt2, str)
    assert len(salt1) == 32  # 16 bytes = 32 hex chars
    assert len(salt2) == 32
    assert salt1 != salt2


def test_password_hashing_deterministic_with_same_salt():
    salt = generate_salt()
    pw = "SuperSecretPassword!42"

    hash1 = hash_password(pw, salt)
    hash2 = hash_password(pw, salt)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex digest = 64 chars


def test_password_hashing_differs_with_different_salts():
    pw = "SamePasswordAcrossUsers"
    salt1 = generate_salt()
    salt2 = generate_salt()

    hash1 = hash_password(pw, salt1)
    hash2 = hash_password(pw, salt2)

    assert hash1 != hash2


def test_create_password_hash_helper():
    pw = "myNewPassword"
    hashed, salt = create_password_hash(pw)

    assert isinstance(hashed, str)
    assert isinstance(salt, str)
    assert verify_password(pw, hashed, salt)


def test_verify_password_matches_and_rejects_incorrect():
    pw = "StudioCreator123#"
    hashed, salt = create_password_hash(pw)

    # Correct password verifies
    assert verify_password(pw, hashed, salt) is True

    # Incorrect password fails
    assert verify_password("WrongPassword!", hashed, salt) is False
    assert verify_password(pw.lower(), hashed, salt) is False

    # Edge cases
    assert verify_password("", hashed, salt) is False
    assert verify_password(pw, "", salt) is False
    assert verify_password(pw, hashed, "") is False


def test_hash_password_empty_inputs_raise_value_error():
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("", "salt123")

    with pytest.raises(ValueError, match="Salt cannot be empty"):
        hash_password("password", "")


def test_jwt_token_generation_and_decoding():
    payload = {"sub": "usr-12345", "role": "creator"}
    token = create_access_token(payload, expires_delta=timedelta(minutes=15))

    assert isinstance(token, str)
    decoded = decode_access_token(token)

    assert decoded["sub"] == "usr-12345"
    assert decoded["role"] == "creator"
    assert "exp" in decoded
    assert "iat" in decoded


def test_jwt_token_expiration():
    payload = {"sub": "usr-expired"}
    # Generate token already expired in the past
    token = create_access_token(payload, expires_delta=timedelta(seconds=-10))

    with pytest.raises(ExpiredTokenError, match="token has expired"):
        decode_access_token(token)


def test_jwt_token_invalid_signature():
    payload = {"sub": "usr-tampered"}
    token = create_access_token(payload, secret_key="a-very-long-and-secure-secret-key-for-testing-32bytes-1")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret_key="a-very-long-and-secure-secret-key-for-testing-32bytes-2")


def test_jwt_token_malformed_string():
    with pytest.raises(InvalidTokenError):
        decode_access_token("this.is.not.a.valid.jwt")

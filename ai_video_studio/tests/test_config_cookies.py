import pytest

from config import resolve_cookie_samesite, resolve_cookie_secure, settings, validate_cookie_config


# --- resolve_cookie_secure / resolve_cookie_samesite: pure default-resolution logic ---


def test_local_default_is_insecure_lax():
    assert resolve_cookie_secure("development", override=None) is False
    assert resolve_cookie_samesite("development", override=None) == "lax"


def test_staging_default_is_secure_none():
    assert resolve_cookie_secure("staging", override=None) is True
    assert resolve_cookie_samesite("staging", override=None) == "none"


def test_production_default_is_secure_none():
    assert resolve_cookie_secure("production", override=None) is True
    assert resolve_cookie_samesite("production", override=None) == "none"


def test_explicit_override_wins_over_environment_default():
    # A same-site staging/prod deployment can opt back into Lax explicitly.
    assert resolve_cookie_secure("production", override=False) is False
    assert resolve_cookie_samesite("production", override="lax") == "lax"
    # And local dev can opt into Secure/None explicitly (e.g. testing HTTPS locally).
    assert resolve_cookie_secure("development", override=True) is True
    assert resolve_cookie_samesite("development", override="none") == "none"


# --- validate_cookie_config: fail-fast checks ---


def test_local_development_default_is_valid():
    validate_cookie_config("development", cookie_secure=False, cookie_samesite="lax")


def test_production_with_secure_true_is_valid():
    validate_cookie_config("production", cookie_secure=True, cookie_samesite="none")


def test_staging_with_secure_true_is_valid():
    validate_cookie_config("staging", cookie_secure=True, cookie_samesite="none")


def test_production_cannot_start_with_cookie_secure_false():
    with pytest.raises(RuntimeError, match="COOKIE_SECURE=false"):
        validate_cookie_config("production", cookie_secure=False, cookie_samesite="none")


def test_staging_cannot_start_with_cookie_secure_false():
    with pytest.raises(RuntimeError, match="COOKIE_SECURE=false"):
        validate_cookie_config("staging", cookie_secure=False, cookie_samesite="lax")


def test_samesite_none_without_secure_raises_in_development():
    """Even in local development, SameSite=None without Secure is a
    browser-invalid cookie (browsers silently drop it) - not just a
    production concern, so this is checked independently of ENVIRONMENT."""
    with pytest.raises(RuntimeError, match="COOKIE_SAMESITE=none requires COOKIE_SECURE=true"):
        validate_cookie_config("development", cookie_secure=False, cookie_samesite="none")


def test_invalid_samesite_value_raises():
    with pytest.raises(RuntimeError, match="COOKIE_SAMESITE must be one of"):
        validate_cookie_config("development", cookie_secure=False, cookie_samesite="invalid")


def test_real_process_settings_pass_validation():
    """The module-level settings this process actually booted with already
    passed validate_cookie_config once at import time (config.py calls it
    right after constructing `settings`) - re-running it here is a cheap
    regression guard that stays true for whatever ENVIRONMENT this test run
    itself is under."""
    validate_cookie_config(settings.ENVIRONMENT, settings.COOKIE_SECURE, settings.COOKIE_SAMESITE)

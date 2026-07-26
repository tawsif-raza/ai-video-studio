import pytest

from publishing_engine.credentials import CredentialProvider, EnvCredentialProvider


def test_credential_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        CredentialProvider()


def test_env_credential_provider_reads_matching_prefixed_variables():
    env = {
        "YOUTUBE_CLIENT_ID": "abc123",
        "YOUTUBE_CLIENT_SECRET": "shh",
        "YOUTUBE_REFRESH_TOKEN": "rt-1",
    }
    provider = EnvCredentialProvider(env=env)

    credentials = provider.load("youtube")

    assert credentials.platform == "youtube"
    assert credentials.fields == {"client_id": "abc123", "client_secret": "shh", "refresh_token": "rt-1"}


def test_env_credential_provider_ignores_unrelated_and_other_platform_variables():
    env = {
        "YOUTUBE_CLIENT_ID": "abc123",
        "TIKTOK_CLIENT_ID": "other-platform-value",
        "GEMINI_API_KEY": "unrelated",
        "PATH": "/usr/bin",
    }
    provider = EnvCredentialProvider(env=env)

    credentials = provider.load("youtube")

    assert credentials.fields == {"client_id": "abc123"}


def test_env_credential_provider_omits_blank_values_entirely():
    env = {"YOUTUBE_CLIENT_ID": "", "YOUTUBE_CLIENT_SECRET": "secret"}
    provider = EnvCredentialProvider(env=env)

    credentials = provider.load("youtube")

    assert "client_id" not in credentials.fields
    assert credentials.fields == {"client_secret": "secret"}


def test_env_credential_provider_returns_empty_fields_when_nothing_configured():
    provider = EnvCredentialProvider(env={})

    credentials = provider.load("youtube")

    assert credentials.platform == "youtube"
    assert credentials.fields == {}


def test_env_credential_provider_is_case_insensitive_to_platform_name_casing():
    env = {"YOUTUBE_CLIENT_ID": "abc123"}
    provider = EnvCredentialProvider(env=env)

    credentials = provider.load("YouTube")

    assert credentials.fields == {"client_id": "abc123"}

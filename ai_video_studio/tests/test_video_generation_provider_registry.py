import pytest

from video_generation_engine.errors import VideoGenerationInputError
from video_generation_engine.provider_registry import resolve_provider
from video_generation_engine.providers.stub import StubProvider


def test_resolve_stub_provider():
    assert resolve_provider("stub") is StubProvider


def test_unknown_provider_raises_naming_registered_providers():
    with pytest.raises(VideoGenerationInputError) as exc:
        resolve_provider("runway")
    assert "runway" in str(exc.value)
    assert "stub" in str(exc.value)


def test_google_veo_is_not_registered():
    # Explicit guard for this milestone's constraint: Google Veo must not be
    # implemented or registered by Milestone V2.
    with pytest.raises(VideoGenerationInputError):
        resolve_provider("google_veo")

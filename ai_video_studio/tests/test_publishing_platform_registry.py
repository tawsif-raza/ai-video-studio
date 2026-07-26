import pytest

from publishing_engine.errors import PublishInputError
from publishing_engine.platforms.registry import resolve_platform
from publishing_engine.platforms.youtube import YouTubePlatform


def test_resolve_platform_returns_youtube_adapter():
    assert resolve_platform("youtube") is YouTubePlatform


def test_resolve_platform_raises_on_unknown_name():
    with pytest.raises(PublishInputError, match="tiktok"):
        resolve_platform("tiktok")


def test_resolve_platform_error_lists_registered_platforms():
    with pytest.raises(PublishInputError, match="youtube"):
        resolve_platform("unknown-platform")

import pytest

from publishing_engine.platforms.base import PublishingPlatform
from publishing_engine.platforms.youtube import YouTubePlatform


def test_publishing_platform_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        PublishingPlatform()


def test_incomplete_subclass_cannot_be_instantiated():
    class IncompletePlatform(PublishingPlatform):
        platform_name = "incomplete"

        def authenticate(self):
            ...

        # upload/check_status deliberately not implemented

    with pytest.raises(TypeError):
        IncompletePlatform()


def test_youtube_platform_implements_the_full_interface():
    platform = YouTubePlatform()

    assert isinstance(platform, PublishingPlatform)
    assert platform.platform_name == "youtube"

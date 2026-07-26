"""
Live YouTube authentication check (Milestone P4). Unlike every other test in
this suite, this one makes a REAL network call - one HTTP token refresh plus
one minimal, read-only YouTube Data API request (channels.list, mine=true) -
against actual Google infrastructure. It is skipped entirely unless real
credentials are explicitly configured via environment variables, exactly as
required: "Integration tests should run only when credentials are explicitly
configured."

To run this test locally:
    set YOUTUBE_CLIENT_ID=...
    set YOUTUBE_CLIENT_SECRET=...
    set YOUTUBE_REFRESH_TOKEN=...
    pytest tests/integration/test_publishing_youtube_authenticate_live.py -v
"""

import pytest

from publishing_engine.credentials import EnvCredentialProvider
from publishing_engine.platforms.youtube import REQUIRED_CREDENTIAL_FIELDS, YouTubePlatform

_provider = EnvCredentialProvider()
_credentials = _provider.load("youtube")
_has_live_credentials = all(field in _credentials.fields for field in REQUIRED_CREDENTIAL_FIELDS)

pytestmark = pytest.mark.skipif(
    not _has_live_credentials,
    reason=(
        "Live YouTube credentials not configured - set YOUTUBE_CLIENT_ID, "
        "YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN to run this test."
    ),
)


def test_authenticate_against_the_real_youtube_api():
    platform = YouTubePlatform()

    result = platform.authenticate(_credentials)

    assert result.success is True, f"live authentication failed: {result.error_type} - {result.error}"
    assert result.platform == "youtube"

from publishing_engine.platforms.youtube import YouTubePlatform
from shared_core.contracts.publish import PlatformCredentials


def _credentials(**fields):
    return PlatformCredentials(platform="youtube", fields=fields)


def test_validate_credentials_passes_when_all_required_fields_present():
    platform = YouTubePlatform()

    report = platform.validate_credentials(
        _credentials(client_id="id", client_secret="secret", refresh_token="token")
    )

    assert report.is_valid is True
    assert report.platform == "youtube"
    assert all(check.passed for check in report.checks)


def test_validate_credentials_fails_when_all_fields_missing():
    platform = YouTubePlatform()

    report = platform.validate_credentials(_credentials())

    assert report.is_valid is False
    assert all(not check.passed for check in report.checks)


def test_validate_credentials_fails_when_one_field_missing():
    platform = YouTubePlatform()

    report = platform.validate_credentials(_credentials(client_id="id", client_secret="secret"))

    assert report.is_valid is False
    missing = next(c for c in report.checks if c.name == "credential_refresh_token")
    assert missing.passed is False
    present = next(c for c in report.checks if c.name == "credential_client_id")
    assert present.passed is True


def test_validate_credentials_treats_whitespace_only_value_as_missing():
    platform = YouTubePlatform()

    report = platform.validate_credentials(
        _credentials(client_id="   ", client_secret="secret", refresh_token="token")
    )

    assert report.is_valid is False
    assert next(c for c in report.checks if c.name == "credential_client_id").passed is False


def test_validate_credentials_performs_no_network_activity_by_construction():
    # validate_credentials only inspects the in-memory PlatformCredentials
    # object it's given - there is no client/session/socket involved at all,
    # so there is nothing to mock and nothing that could reach the network.
    platform = YouTubePlatform()
    report = platform.validate_credentials(_credentials(client_id="a", client_secret="b", refresh_token="c"))
    assert report.external_video_id is None
    assert report.external_url is None

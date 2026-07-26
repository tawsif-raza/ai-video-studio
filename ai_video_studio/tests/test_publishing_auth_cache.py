from publishing_engine.auth_cache import AuthenticationCache, fingerprint_credentials
from shared_core.contracts.publish import AuthenticationResult, PlatformCredentials


class _FakeClock:
    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _success():
    return AuthenticationResult(success=True, platform="youtube", account_label="Chan")


def _failure():
    return AuthenticationResult(success=False, platform="youtube", error="boom", error_type="api_error")


def test_fingerprint_is_stable_for_identical_fields():
    a = PlatformCredentials(platform="youtube", fields={"client_id": "x", "client_secret": "y"})
    b = PlatformCredentials(platform="youtube", fields={"client_secret": "y", "client_id": "x"})  # different order
    assert fingerprint_credentials(a) == fingerprint_credentials(b)


def test_fingerprint_differs_for_different_values():
    a = PlatformCredentials(platform="youtube", fields={"client_id": "x"})
    b = PlatformCredentials(platform="youtube", fields={"client_id": "y"})
    assert fingerprint_credentials(a) != fingerprint_credentials(b)


def test_first_call_always_authenticates():
    clock = _FakeClock()
    cache = AuthenticationCache(clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    result = cache.get_or_authenticate(("youtube", "fp"), authenticate)

    assert result.success is True
    assert len(calls) == 1


def test_cache_hit_within_ttl_skips_a_second_call():
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=300, min_interval_seconds=5, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fp"), authenticate)
    clock.advance(10)
    cache.get_or_authenticate(("youtube", "fp"), authenticate)

    assert len(calls) == 1


def test_cache_expires_after_ttl_and_reauthenticates():
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=60, min_interval_seconds=1, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fp"), authenticate)
    clock.advance(61)
    cache.get_or_authenticate(("youtube", "fp"), authenticate)

    assert len(calls) == 2


def test_rate_limit_serves_stale_cached_result_instead_of_reattempting():
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=5, min_interval_seconds=30, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fp"), authenticate)
    clock.advance(10)  # past ttl (5s) but within min_interval (30s)
    result = cache.get_or_authenticate(("youtube", "fp"), authenticate)

    assert len(calls) == 1  # not re-attempted
    assert result.success is True  # served the stale-but-recent result


def test_rotated_credentials_right_after_a_recent_attempt_are_rate_limited_not_reattempted():
    # Rate limiting is tracked per PLATFORM, not per credential fingerprint -
    # a real attempt with credentials A consumes the platform's budget, so
    # rotating to credentials B immediately after gets no cached result yet
    # AND is still rate-limited: a synthesized failure, not a second real call.
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=5, min_interval_seconds=30, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fingerprint-a"), authenticate)
    clock.advance(2)  # well within min_interval_seconds=30
    result = cache.get_or_authenticate(("youtube", "fingerprint-b"), authenticate)

    assert len(calls) == 1  # second (different-credential) attempt was NOT made
    assert result.success is False
    assert result.error_type == "rate_limited"


def test_different_credentials_both_attempted_once_rate_limit_window_has_passed():
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=5, min_interval_seconds=1, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fingerprint-a"), authenticate)
    clock.advance(2)  # past min_interval_seconds=1
    cache.get_or_authenticate(("youtube", "fingerprint-b"), authenticate)

    assert len(calls) == 2  # different fingerprint, and outside the rate-limit window - both attempted


def test_rate_limiting_is_scoped_per_platform_not_globally():
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=5, min_interval_seconds=30, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fp"), authenticate)
    clock.advance(1)  # within youtube's rate-limit window
    result = cache.get_or_authenticate(("tiktok", "fp"), authenticate)

    assert len(calls) == 2  # a different platform's budget is untouched by youtube's recent attempt
    assert result.success is True


def test_clear_resets_cache_and_rate_limit_state():
    clock = _FakeClock()
    cache = AuthenticationCache(ttl_seconds=300, min_interval_seconds=300, clock=clock)
    calls = []

    def authenticate():
        calls.append(1)
        return _success()

    cache.get_or_authenticate(("youtube", "fp"), authenticate)
    cache.clear()
    cache.get_or_authenticate(("youtube", "fp"), authenticate)

    assert len(calls) == 2

"""
In-memory cache + rate limiter around PublishingPlatform.authenticate()
(Milestone P5). authenticate() makes a real network call; repeated readiness
checks (a CLI invoked repeatedly, a future scheduler polling readiness) must
not re-authenticate on every single call.

- Caching: a result (success or failure) is reused for ttl_seconds before a
  fresh attempt is made for that exact (platform, credentials) pair.
- Rate limiting: tracked per PLATFORM, not per credential fingerprint - a
  real authentication attempt (regardless of which credentials) consumes the
  platform's rate-limit budget, since the underlying constraint being
  protected (the token endpoint / API quota) is the platform's, not tied to
  any one credential. This means rotating to different credentials right
  after a recent attempt does NOT bypass the limit: with no cached result
  yet for the new credentials, the caller gets a synthesized "rate_limited"
  failure rather than a second real call within the interval.

Result caching stays keyed by (platform, fingerprint_credentials(credentials))
so a credential change is its own cache entry - a stale verdict is never
served for different credentials, only a rate-limit notice when there's
nothing cached for them yet.
"""

import hashlib
import json
import time
from typing import Callable, Dict, Tuple

from shared_core.contracts.publish import AuthenticationResult, PlatformCredentials

CacheKey = Tuple[str, str]


def fingerprint_credentials(credentials: PlatformCredentials) -> str:
    """A one-way fingerprint of credential VALUES, never the values
    themselves - used only to detect "these are different credentials than
    last time" so a cache entry can never mask a genuine credential change.
    A SHA-256 digest cannot be reversed to recover the original fields."""
    serialized = json.dumps(sorted(credentials.fields.items()))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class AuthenticationCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        min_interval_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl_seconds = ttl_seconds
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._entries: Dict[CacheKey, Tuple[AuthenticationResult, float]] = {}
        self._last_attempt_at: Dict[str, float] = {}  # keyed by platform only

    def get_or_authenticate(
        self, key: CacheKey, authenticate: Callable[[], AuthenticationResult]
    ) -> AuthenticationResult:
        platform, _fingerprint = key
        now = self._clock()

        cached = self._entries.get(key)
        if cached is not None and now - cached[1] < self._ttl_seconds:
            return cached[0]

        last_attempt = self._last_attempt_at.get(platform)
        if last_attempt is not None and now - last_attempt < self._min_interval_seconds:
            if cached is not None:
                return cached[0]  # a stale-but-recent result for these exact credentials
            return AuthenticationResult(
                success=False,
                platform=platform,
                error="authentication rate-limited - a previous attempt for this platform is still within the minimum retry interval",
                error_type="rate_limited",
            )

        self._last_attempt_at[platform] = now
        result = authenticate()
        self._entries[key] = (result, now)
        return result

    def clear(self) -> None:
        self._entries.clear()
        self._last_attempt_at.clear()

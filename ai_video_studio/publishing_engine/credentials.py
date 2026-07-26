"""
Credential provider abstraction (ARCHITECTURE.md SS24.9's previously-deferred
decision, resolved in Milestone P4): *where* credential values come from, kept
separate from *what a platform does with them* (PublishingPlatform.
authenticate/validate_credentials). Structural-only validation (Milestone P3)
never needed a source at all - only a real authenticate() call does.

Stdlib-only, so publishing_engine still depends on nothing beyond shared_core
and itself - no project_manager, no config.py. A future milestone that wants
project-scoped or file-based credentials can add another CredentialProvider
implementation, or compose one outside this package, without changing this
interface or any platform adapter.
"""

import os
from abc import ABC, abstractmethod
from typing import Mapping, Optional

from shared_core.contracts.publish import PlatformCredentials


class CredentialProvider(ABC):
    """Abstraction over credential sourcing. A platform adapter never reads
    an environment variable, a file, or a secrets manager itself - it only
    ever receives an already-loaded PlatformCredentials."""

    @abstractmethod
    def load(self, platform: str) -> PlatformCredentials:
        ...


class EnvCredentialProvider(CredentialProvider):
    """Reads credential fields from environment variables named
    "<PLATFORM>_<FIELD>" in upper case - e.g. platform="youtube" reads
    YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN into
    fields {"client_id": ..., "client_secret": ..., "refresh_token": ...}.
    Purely mechanical: it has no built-in knowledge of which fields a given
    platform actually needs (that's the adapter's job, e.g.
    YouTubePlatform.REQUIRED_CREDENTIAL_FIELDS) - it just reads whatever
    matches the naming convention and is non-empty. A variable that's unset
    or blank is omitted entirely, not recorded as an empty string, so a
    downstream presence check behaves identically to a field that was never
    set at all."""

    def __init__(self, *, env: Optional[Mapping[str, str]] = None):
        self._env = env if env is not None else os.environ

    def load(self, platform: str) -> PlatformCredentials:
        prefix = f"{platform.upper()}_"
        fields = {
            key[len(prefix):].lower(): value
            for key, value in self._env.items()
            if key.startswith(prefix) and value
        }
        return PlatformCredentials(platform=platform, fields=fields)

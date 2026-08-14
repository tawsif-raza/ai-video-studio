"""
Pure name -> implementation lookup for video generation providers
(ARCHITECTURE.md SS25.5), mirroring publishing_engine.platforms.registry
exactly. Adding a provider means adding one entry here and nowhere else -
zero changes to the controller, the contracts, or any other provider's code.

Milestone V2 (Stub Provider Foundation) registered exactly one provider,
"stub" - the zero-cost local placeholder generator - under a non-default
name on purpose: VideoGenerationOptions.provider defaults to "google_veo"
(shared_core/contracts/video_generation.py), which had no registered adapter
yet in V2, so resolving the bare default failed closed with
VideoGenerationInputError rather than silently reaching for the stub.

Milestone V3 (Real Google Veo Provider) registers "google_veo"
(video_generation_engine/providers/google_veo.py) - the first real,
network-backed provider. A bare-default VideoGenerationOptions now resolves
to it; GoogleVeoProvider.authenticate() is what actually gates whether it's
usable (missing credentials report ProviderInfo(available=False, ...), which
the controller turns into VideoGenerationEnvironmentError - resolution
itself never fails just because credentials happen to be unset).
"""

from typing import Dict, Type

from video_generation_engine.errors import VideoGenerationInputError
from video_generation_engine.providers.base import VideoGenerationProvider
from video_generation_engine.providers.google_veo import GoogleVeoProvider
from video_generation_engine.providers.stub import StubProvider

_PROVIDER_REGISTRY: Dict[str, Type[VideoGenerationProvider]] = {
    "stub": StubProvider,
    "google_veo": GoogleVeoProvider,
}


def resolve_provider(name: str) -> Type[VideoGenerationProvider]:
    """Pure name -> implementation lookup. Raises VideoGenerationInputError
    for an unregistered name, naming every currently-registered provider so
    the caller can see what's actually available."""
    try:
        return _PROVIDER_REGISTRY[name]
    except KeyError:
        registered = ", ".join(sorted(_PROVIDER_REGISTRY)) or "none"
        raise VideoGenerationInputError(
            f"Unknown video generation provider '{name}'. Registered providers: {registered}."
        )

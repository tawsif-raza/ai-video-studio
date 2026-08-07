"""
Pure name -> implementation lookup for video generation providers
(ARCHITECTURE.md SS25.5), mirroring publishing_engine.platforms.registry
exactly. Adding a provider means adding one entry here and nowhere else -
zero changes to the controller, the contracts, or any other provider's code.

Milestone V2 (Stub Provider Foundation) registers exactly one provider,
"stub" - the zero-cost local placeholder generator. It is registered under a
non-default name on purpose: VideoGenerationOptions.provider still defaults
to "google_veo" (shared_core/contracts/video_generation.py), which has no
registered adapter yet, so resolving the bare default fails closed with
VideoGenerationInputError rather than silently reaching for the stub. No
Google Veo (or any other real provider) is implemented or registered by this
milestone (ARCHITECTURE.md SS25.15).
"""

from typing import Dict, Type

from video_generation_engine.errors import VideoGenerationInputError
from video_generation_engine.providers.base import VideoGenerationProvider
from video_generation_engine.providers.stub import StubProvider

_PROVIDER_REGISTRY: Dict[str, Type[VideoGenerationProvider]] = {
    "stub": StubProvider,
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

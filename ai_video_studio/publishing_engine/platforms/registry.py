from typing import Dict, Type

from publishing_engine.errors import PublishInputError
from publishing_engine.platforms.base import PublishingPlatform
from publishing_engine.platforms.youtube import YouTubePlatform

_PLATFORM_REGISTRY: Dict[str, Type[PublishingPlatform]] = {
    "youtube": YouTubePlatform,
}


def resolve_platform(name: str) -> Type[PublishingPlatform]:
    """Pure name -> implementation lookup (ARCHITECTURE.md SS24.2). Adding a
    second platform means adding one entry here and nowhere else."""
    try:
        return _PLATFORM_REGISTRY[name]
    except KeyError:
        registered = ", ".join(sorted(_PLATFORM_REGISTRY)) or "none"
        raise PublishInputError(
            f"Unknown publishing platform '{name}'. Registered platforms: {registered}."
        )

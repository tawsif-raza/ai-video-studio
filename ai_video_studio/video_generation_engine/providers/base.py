"""
Abstract interface every video generation provider adapter implements
(ARCHITECTURE.md SS25.5). The controller and every contract are written
against this interface only - they never know they're talking to Google Veo,
a local stub, or anything else specifically. Adding a new provider means
writing one class that implements this interface and registering it in
provider_registry.py - zero changes here, in the controller, or in any other
provider's code. Mirrors publishing_engine.platforms.base.PublishingPlatform.

Each method is boundary (real I/O - network for a real provider, a local
ffmpeg subprocess for the stub) and, past the pre-flight stage, never raises
for a failure that happens once the call is actually made - it returns a
structured result instead (VideoGenerationResult / VideoGenerationStatus),
the same "reportable, not exceptional" convention execution_engine's and
publishing_engine's boundary modules already established.
"""

from abc import ABC, abstractmethod

from shared_core.contracts.video_generation import (
    ProviderInfo,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationStatus,
)


class VideoGenerationProvider(ABC):
    provider_name: str

    @abstractmethod
    def authenticate(self) -> ProviderInfo:
        """Resolve credentials (if any) and confirm the provider is usable.
        Mirrors ffmpeg_detector.detect_ffmpeg / PublishingPlatform.authenticate
        - reports availability as data, never raises itself. The controller
        decides whether an unavailable provider is fatal
        (VideoGenerationEnvironmentError)."""
        ...

    @abstractmethod
    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Submit (and, for a synchronous provider, complete) the generation
        job. Most real video providers are asynchronous (submit -> poll ->
        download), so retry/backoff and any poll loop live inside this call,
        not the controller (ARCHITECTURE.md SS25.5). Never raises for a
        failed generation - always returns a VideoGenerationResult."""
        ...

    @abstractmethod
    def check_status(self, external_job_id: str) -> VideoGenerationStatus:
        """Poll for async completion - same shape and role as
        PublishingPlatform.check_status(). A synchronous provider (the local
        stub) has no real job to poll and reports an immediate terminal
        status for shape symmetry only."""
        ...

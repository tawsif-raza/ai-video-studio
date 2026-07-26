"""Platform abstraction for the Publishing Engine (ARCHITECTURE.md SS24.2):
one PublishingPlatform implementation per external platform, selected by
name through registry.resolve_platform - the controller and every contract
are written against the PublishingPlatform interface only."""

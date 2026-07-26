"""
The Publishing Engine (ARCHITECTURE.md SS24) - the fourth top-level
component: VIDEO_RENDERED -> PUBLISHED. As of Milestone P5: platform
abstraction (P1), preflight readiness validation (P2), structural credential
validation (P3), and real (rate-limited/cached) authentication (P4) are all
wired together by PublishingEngineController.run() into one
ReadyToPublishResult - exercised end-to-end via publish_app.py. Upload,
thumbnail upload, metadata submission, status polling, publish reports, and
the PUBLISHED state transition remain later milestones' jobs.
"""

from publishing_engine.controller import PublishingEngineController
from publishing_engine.errors import PublishError, PublishInputError

__all__ = [
    "PublishingEngineController",
    "PublishError",
    "PublishInputError",
]

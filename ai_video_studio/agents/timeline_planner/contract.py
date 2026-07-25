from typing import List

from pydantic import BaseModel

from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.timeline import ShotDuration, Timeline, TimelineClip, VoiceSegment

__all__ = ["ShotDuration", "Timeline", "TimelineClip", "TimelinePlannerInput", "ValidatedAssetManifest", "VoiceSegment"]


class TimelinePlannerInput(BaseModel):
    """Typed input assembled by Project Manager: the approved media manifest
    from Asset Validation, plus every shot's planned duration."""

    asset_manifest: ValidatedAssetManifest
    shot_durations: List[ShotDuration]

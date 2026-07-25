from pydantic import BaseModel

from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline

__all__ = [
    "EditingPlan", "EditingPlannerInput", "EditingSegment", "MusicPlan", "SubtitlePlan", "Timeline",
    "ValidatedAssetManifest",
]


class EditingPlannerInput(BaseModel):
    """Typed input assembled by Project Manager: every earlier Producer
    Studio artifact this stage merges. No new Production Package file needs
    reading directly - validated assets, subtitles, and music are already
    fully captured in these four typed objects, each itself derived from the
    Production Package by the stage before it."""

    asset_manifest: ValidatedAssetManifest
    timeline: Timeline
    subtitle_plan: SubtitlePlan
    music_plan: MusicPlan

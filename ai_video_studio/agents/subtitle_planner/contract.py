from typing import List

from pydantic import BaseModel

from shared_core.contracts.subtitle import SubtitleCue, SubtitlePlan
from shared_core.contracts.timeline import Timeline, VoiceSegment

__all__ = ["SubtitleCue", "SubtitlePlan", "SubtitlePlannerInput", "Timeline", "VoiceSegment"]


class SubtitlePlannerInput(BaseModel):
    """Typed input assembled by Project Manager: the Timeline (for each
    scene's narration time window, via voice_segments) plus the narration
    text, split into per-scene paragraphs in the same ascending scene_id
    order voice_segments already appear in - so they can be paired
    positionally without needing a typed, reloadable VoiceScript (which, like
    ShotPlan, has no legacy flat-file form). narration_paragraphs is empty
    when the Voice Script stage was skipped."""

    timeline: Timeline
    narration_paragraphs: List[str]

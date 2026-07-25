from typing import List

from pydantic import BaseModel

from shared_core.contracts.music_plan import DuckWindow, MusicCue, MusicPlan, SceneMood
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline

__all__ = [
    "DuckWindow", "MusicCue", "MusicPlan", "MusicPlannerInput", "SceneMood", "SubtitlePlan", "Timeline",
]


class MusicPlannerInput(BaseModel):
    """Typed input assembled by Project Manager: the Timeline (for each
    scene's time window, via its clips), the SubtitlePlan (for narration
    ducking windows, one per subtitle cue), and each scene's mood, read from
    the Production Package's scene_plan.json."""

    timeline: Timeline
    subtitle_plan: SubtitlePlan
    scene_moods: List[SceneMood]

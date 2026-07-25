from collections import defaultdict
from typing import Dict, List, Tuple

from agents.base.exceptions import ContractViolationError
from agents.music_planner.contract import MusicPlannerInput
from shared_core.contracts.music_plan import DuckWindow, MusicCue, MusicPlan
from shared_core.contracts.timeline import TimelineClip

# A cue this short can't meaningfully hold a fade-in and fade-out, so it's
# planned as silence rather than a barely-audible sliver of music.
MIN_MUSIC_DURATION_SECONDS = 1.5

# Fades at the very start/end of the whole timeline are longer (ramping from
# true silence) than fades at an interior scene boundary (a quicker
# mood-to-mood crossfade, since the previous/next cue is already playing).
EDGE_FADE_SECONDS = 1.5
BOUNDARY_FADE_SECONDS = 1.0

SILENCE_KEYWORDS = ("silence", "silent", "stillness", "hush")

# (keywords, mood_label, tempo, intensity), checked in order - first match
# wins. Free-text mood strings from Director Studio aren't a fixed vocabulary,
# so this is a best-effort keyword classifier with a neutral fallback rather
# than a lookup requiring an exact match.
MOOD_RULES: List[Tuple[Tuple[str, ...], str, str, str]] = [
    (("tense", "danger", "afraid", "fear", "urgent", "panic", "caution", "hesitant", "uncertain"),
     "tense", "fast", "high"),
    (("hopeful", "determined", "triumph", "joy", "excited", "brave", "courage", "confiden", "proud", "empower"),
     "uplifting", "medium", "medium-high"),
    (("calm", "peaceful", "quiet", "gentle", "serene", "misty", "soft"),
     "calm", "slow", "low"),
    (("sad", "somber", "melancholy", "grief", "loss", "lonely"),
     "somber", "slow", "low"),
]

DEFAULT_MOOD_LABEL = "neutral"
DEFAULT_TEMPO = "medium"
DEFAULT_INTENSITY = "medium"


def _classify_mood(raw_mood: str) -> Tuple[str, str, str]:
    text = raw_mood.lower()
    for keywords, label, tempo, intensity in MOOD_RULES:
        if any(keyword in text for keyword in keywords):
            return label, tempo, intensity
    return DEFAULT_MOOD_LABEL, DEFAULT_TEMPO, DEFAULT_INTENSITY


def _is_silent(raw_mood: str, duration: float) -> bool:
    text = raw_mood.lower()
    if any(keyword in text for keyword in SILENCE_KEYWORDS):
        return True
    return duration < MIN_MUSIC_DURATION_SECONDS


def _scene_windows(clips: List[TimelineClip]) -> List[Tuple[int, float, float]]:
    """Groups clips by scene, preserving first-appearance order and
    aggregating min-start/max-end - the same grouping Timeline Planning
    itself uses to build voice_segments."""
    order: List[int] = []
    bounds: Dict[int, Tuple[float, float]] = {}
    for clip in clips:
        if clip.scene_id not in bounds:
            order.append(clip.scene_id)
            bounds[clip.scene_id] = (clip.start_time, clip.end_time)
        else:
            low, high = bounds[clip.scene_id]
            bounds[clip.scene_id] = (min(low, clip.start_time), max(high, clip.end_time))
    return [(scene_id, bounds[scene_id][0], bounds[scene_id][1]) for scene_id in order]


def _duck_windows_by_scene(subtitle_plan) -> Dict[int, List[DuckWindow]]:
    grouped: Dict[int, List[DuckWindow]] = defaultdict(list)
    for cue in subtitle_plan.cues:
        grouped[cue.scene_id].append(DuckWindow(start_time=cue.start_time, end_time=cue.end_time))
    return grouped


def build_music_plan(input_data: MusicPlannerInput) -> MusicPlan:
    """Derives a per-scene music strategy from Timeline's scene windows,
    Production Package moods, and SubtitlePlan's narration timing - the
    entry point for Producer Studio's Music Planning stage (ARCHITECTURE.md
    SS6/SS12).

    Runs no LLM and makes no creative decisions beyond a keyword-based mood
    classifier - no music is generated, selected, downloaded, or mixed here,
    only planned for a later stage to execute."""
    timeline = input_data.timeline
    mood_by_scene: Dict[int, str] = {m.scene_id: m.mood for m in input_data.scene_moods}
    duck_windows_by_scene = _duck_windows_by_scene(input_data.subtitle_plan)

    windows = _scene_windows(timeline.clips)
    if not windows:
        return MusicPlan(
            source_timeline_id=timeline.timeline_id, cues=[], total_duration_seconds=timeline.total_duration_seconds
        )

    for scene_id, _, _ in windows:
        if scene_id not in mood_by_scene:
            raise ContractViolationError(
                f"No mood found for scene {scene_id} - Music Planning requires scene_moods to "
                f"cover every scene present on the Timeline"
            )

    cues: List[MusicCue] = []
    last_index = len(windows) - 1
    for i, (scene_id, start, end) in enumerate(windows):
        duration = end - start
        raw_mood = mood_by_scene[scene_id]

        if _is_silent(raw_mood, duration):
            cues.append(MusicCue(
                scene_id=scene_id, start_time=start, end_time=end,
                mood=DEFAULT_MOOD_LABEL, tempo="none", intensity="none", is_silent=True,
            ))
            continue

        mood_label, tempo, intensity = _classify_mood(raw_mood)
        fade_in = EDGE_FADE_SECONDS if i == 0 else BOUNDARY_FADE_SECONDS
        fade_out = EDGE_FADE_SECONDS if i == last_index else BOUNDARY_FADE_SECONDS
        fade_in = min(fade_in, duration / 2)
        fade_out = min(fade_out, duration / 2)

        cues.append(MusicCue(
            scene_id=scene_id, start_time=start, end_time=end,
            mood=mood_label, tempo=tempo, intensity=intensity, is_silent=False,
            fade_in_seconds=fade_in, fade_out_seconds=fade_out,
            duck_windows=duck_windows_by_scene.get(scene_id, []),
        ))

    return MusicPlan(
        source_timeline_id=timeline.timeline_id, cues=cues, total_duration_seconds=timeline.total_duration_seconds
    )

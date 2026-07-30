from typing import Dict, List

from agents.base.exceptions import ContractViolationError
from agents.editing_planner.contract import EditingPlannerInput
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment, compute_final_duration_seconds
from shared_core.contracts.music_plan import MusicCue
from shared_core.contracts.subtitle import SubtitleCue
from shared_core.contracts.timeline import TimelineClip

# A still image needs a placeholder animation to avoid looking static on
# screen; a video clip already has its own motion. Names only - no effect is
# actually applied here, this is a hook for a future effects stage.
IMAGE_EFFECTS_PLACEHOLDERS = ["ken_burns"]
VIDEO_EFFECTS_PLACEHOLDERS: List[str] = []


def _validate_source_chain(input_data: EditingPlannerInput) -> None:
    """Confirms every artifact being merged actually descends from the same
    Timeline - Editing Planning is the first stage to combine three sibling
    outputs (Timeline, SubtitlePlan, MusicPlan), so a stale or swapped
    artifact from a different run must be caught here rather than silently
    producing a blueprint that points at mismatched timing."""
    timeline = input_data.timeline
    if timeline.source_asset_manifest_id != input_data.asset_manifest.manifest_id:
        raise ContractViolationError(
            f"Timeline {timeline.timeline_id} was built from asset manifest "
            f"{timeline.source_asset_manifest_id}, not the provided manifest "
            f"{input_data.asset_manifest.manifest_id}"
        )
    if input_data.subtitle_plan.source_timeline_id != timeline.timeline_id:
        raise ContractViolationError(
            f"SubtitlePlan {input_data.subtitle_plan.subtitle_plan_id} was built from timeline "
            f"{input_data.subtitle_plan.source_timeline_id}, not the provided timeline {timeline.timeline_id}"
        )
    if input_data.music_plan.source_timeline_id != timeline.timeline_id:
        raise ContractViolationError(
            f"MusicPlan {input_data.music_plan.music_plan_id} was built from timeline "
            f"{input_data.music_plan.source_timeline_id}, not the provided timeline {timeline.timeline_id}"
        )


def _subtitle_cue_indices_for_clip(clip: TimelineClip, cues: List[SubtitleCue]) -> List[int]:
    """A subtitle cue belongs to every clip its time window overlaps - a
    sentence can outlast a single shot's duration, so this is a many-to-many
    match by interval overlap, not a one-to-one lookup."""
    return [
        cue.sequence_index for cue in cues
        if cue.start_time < clip.end_time and cue.end_time > clip.start_time
    ]


def _effects_placeholders_for(asset_type: str) -> List[str]:
    return list(IMAGE_EFFECTS_PLACEHOLDERS) if asset_type == "image" else list(VIDEO_EFFECTS_PLACEHOLDERS)


def _transition_for(index: int, last_index: int, scene_id: int, prev_scene_id, next_scene_id) -> tuple:
    """Hard cuts between shots within the same scene, a crossfade at scene
    boundaries (a mood/music change deserves a softer transition than a
    within-scene cut), and a fade from/to black at the very start/end of the
    whole edit."""
    transition_in = "fade_from_black" if index == 0 else ("crossfade" if scene_id != prev_scene_id else "cut")
    transition_out = "fade_to_black" if index == last_index else ("crossfade" if scene_id != next_scene_id else "cut")
    return transition_in, transition_out


def _validate_segments_contiguous(segments: List[EditingSegment], expected_total: float) -> None:
    for prev, nxt in zip(segments, segments[1:]):
        if nxt.start_time != prev.end_time:
            raise ContractViolationError(
                f"Editing segments for shot {prev.shot_id} and {nxt.shot_id} are not contiguous "
                f"({prev.end_time} != {nxt.start_time}) - synchronization with the Timeline is broken"
            )
    if segments and segments[-1].end_time != expected_total:
        raise ContractViolationError(
            f"Editing plan ends at {segments[-1].end_time}, but Timeline's total duration is "
            f"{expected_total} - synchronization with the Timeline is broken"
        )


def build_editing_plan(input_data: EditingPlannerInput) -> EditingPlan:
    """Merges Timeline, SubtitlePlan, and MusicPlan into one deterministic
    editing blueprint - the entry point for Producer Studio's Editing
    Planning stage (ARCHITECTURE.md SS6/SS12).

    Runs no LLM and executes nothing: no rendering, mixing, or subtitle
    burning happens here, only cross-referencing and transition/effects
    planning over data every earlier stage already computed."""
    _validate_source_chain(input_data)

    timeline = input_data.timeline
    music_by_scene: Dict[int, MusicCue] = {cue.scene_id: cue for cue in input_data.music_plan.cues}

    for clip in timeline.clips:
        if clip.scene_id not in music_by_scene:
            raise ContractViolationError(
                f"No music cue found for scene {clip.scene_id} - Editing Planning requires "
                f"MusicPlan to cover every scene present on the Timeline"
            )

    segments: List[EditingSegment] = []
    last_index = len(timeline.clips) - 1
    for i, clip in enumerate(timeline.clips):
        prev_scene_id = timeline.clips[i - 1].scene_id if i > 0 else None
        next_scene_id = timeline.clips[i + 1].scene_id if i < last_index else None
        transition_in, transition_out = _transition_for(i, last_index, clip.scene_id, prev_scene_id, next_scene_id)

        segments.append(EditingSegment(
            scene_id=clip.scene_id,
            shot_id=clip.shot_id,
            asset_path=clip.asset_path,
            asset_type=clip.asset_type,
            start_time=clip.start_time,
            end_time=clip.end_time,
            subtitle_cue_indices=_subtitle_cue_indices_for_clip(clip, input_data.subtitle_plan.cues),
            music_cue_scene_id=clip.scene_id,
            transition_in=transition_in,
            transition_out=transition_out,
            effects_placeholders=_effects_placeholders_for(clip.asset_type),
        ))

    _validate_segments_contiguous(segments, timeline.total_duration_seconds)

    return EditingPlan(
        source_timeline_id=timeline.timeline_id,
        source_subtitle_plan_id=input_data.subtitle_plan.subtitle_plan_id,
        source_music_plan_id=input_data.music_plan.music_plan_id,
        segments=segments,
        # Not timeline.total_duration_seconds: that is the raw, contiguous sum
        # of shot durations, but scene-boundary crossfades (assigned just
        # above via _transition_for) overlap and shrink the actual rendered
        # runtime below that sum - see compute_final_duration_seconds.
        total_duration_seconds=compute_final_duration_seconds(segments),
    )

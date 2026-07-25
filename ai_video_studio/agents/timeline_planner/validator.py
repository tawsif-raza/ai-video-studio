from typing import Dict, List, Tuple

from agents.base.exceptions import ContractViolationError
from agents.timeline_planner.contract import TimelinePlannerInput
from shared_core.contracts.asset_manifest import ValidatedAsset
from shared_core.contracts.timeline import Timeline, TimelineClip, VoiceSegment


def _resolve_clip_asset(asset: ValidatedAsset) -> Tuple[str, str]:
    """Video is preferred over a static image when a shot has both - a video
    clip is closer to the final cut than a still frame stretched to fill the
    shot's duration."""
    if asset.video_path is not None:
        return asset.video_path, "video"
    return asset.image_path, "image"


def build_timeline(input_data: TimelinePlannerInput) -> Timeline:
    """Determines clip order, computes cumulative start/end times, and
    associates each scene's narration window with its clips - the entry point
    for Producer Studio's Timeline Planning stage (ARCHITECTURE.md SS6/SS12).

    This agent runs no LLM and makes no creative decisions - it is pure
    sequencing and arithmetic over data Asset Validation already approved, so
    unlike LLM-backed agents' validators, there is no "business rule" to raise
    ContractViolationError over except a defensive guard against being called
    with a manifest that never actually passed validation."""
    manifest = input_data.asset_manifest
    if not manifest.is_valid:
        raise ContractViolationError(
            "Timeline Planning requires a ValidatedAssetManifest that passed validation "
            f"(manifest {manifest.manifest_id} has is_valid=False)"
        )

    duration_by_slot: Dict[Tuple[int, int], int] = {
        (d.scene_id, d.shot_id): d.duration_seconds for d in input_data.shot_durations
    }

    ordered_assets = sorted(manifest.assets, key=lambda a: (a.scene_id, a.shot_id))

    clips: List[TimelineClip] = []
    cursor = 0.0
    for asset in ordered_assets:
        slot = (asset.scene_id, asset.shot_id)
        if slot not in duration_by_slot:
            raise ContractViolationError(
                f"No planned duration found for scene {asset.scene_id} shot {asset.shot_id} - "
                f"Timeline Planning requires shot_durations to cover every validated asset"
            )
        asset_path, asset_type = _resolve_clip_asset(asset)
        duration = duration_by_slot[slot]
        start, end = cursor, cursor + duration
        clips.append(TimelineClip(
            scene_id=asset.scene_id,
            shot_id=asset.shot_id,
            asset_path=asset_path,
            asset_type=asset_type,
            duration_seconds=duration,
            start_time=start,
            end_time=end,
        ))
        cursor = end

    voice_segments: List[VoiceSegment] = []
    if manifest.narration_audio_path is not None:
        scenes_in_order: List[int] = []
        scene_bounds: Dict[int, Tuple[float, float]] = {}
        for clip in clips:
            if clip.scene_id not in scene_bounds:
                scenes_in_order.append(clip.scene_id)
                scene_bounds[clip.scene_id] = (clip.start_time, clip.end_time)
            else:
                low, high = scene_bounds[clip.scene_id]
                scene_bounds[clip.scene_id] = (min(low, clip.start_time), max(high, clip.end_time))

        for scene_id in scenes_in_order:
            start, end = scene_bounds[scene_id]
            voice_segments.append(VoiceSegment(
                scene_id=scene_id, start_time=start, end_time=end, audio_path=manifest.narration_audio_path
            ))

    return Timeline(
        source_asset_manifest_id=manifest.manifest_id,
        clips=clips,
        voice_segments=voice_segments,
        total_duration_seconds=cursor,
    )

# Producer Studio's package writer, owned by Project Manager (ARCHITECTURE.md
# SS4/SS6/SS9) - the Producer Package's shape is defined once, as typed schemas
# in shared_core/contracts, exactly like the Production Package; this module
# only serializes instances of those types to disk. Currently writes
# asset_manifest.json (Milestone 1), timeline_plan.json (Milestone 2),
# subtitle_plan.json (Milestone 3), music_plan.json (Milestone 4),
# editing_plan.json (Milestone 5), thumbnail_plan.json (Milestone 6), and
# publishing_metadata.json (Milestone 7) - the six planning outputs that,
# together, mean the project is EDIT_PLAN_READY. This grew file-by-file the
# same way package_writer.py did across Director Studio's phases.

import json
from pathlib import Path
from typing import Optional

from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.publishing_metadata import PublishingPlan
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.thumbnail_plan import ThumbnailPlan
from shared_core.contracts.timeline import Timeline
from config import settings

MANIFEST_DESCRIPTIONS = {
    "asset_manifest.json": "Per-shot media coverage report from Asset Validation: missing, duplicate, and naming issues.",
    "timeline_plan.json": "Clip ordering, start/end times, and per-scene voice segments from Timeline Planning.",
    "subtitle_plan.json": "Time-aligned subtitle cues from Subtitle Planning, ready for future SRT/VTT export.",
    "music_plan.json": "Per-scene music strategy from Music Planning: mood, tempo, intensity, fades, and narration ducking.",
    "editing_plan.json": "Deterministic editing blueprint from Editing Planning: merged assets, subtitles, music, transitions, and effects placeholders.",
    "thumbnail_plan.json": "Thumbnail strategy from Thumbnail Planning: composition, focal subject, emotion, text-safe areas, and a generation prompt per variant.",
    "publishing_metadata.json": "Canonical and YouTube-specific publishing metadata from Publishing Planning: title, description, keywords, hashtags, category, playlist, and visibility.",
}


def write_producer_package(
    *,
    project_id: str,
    asset_manifest: ValidatedAssetManifest,
    timeline: Optional[Timeline] = None,
    subtitle_plan: Optional[SubtitlePlan] = None,
    music_plan: Optional[MusicPlan] = None,
    editing_plan: Optional[EditingPlan] = None,
    thumbnail_plan: Optional[ThumbnailPlan] = None,
    publishing_plan: Optional[PublishingPlan] = None,
) -> Path:
    """Writes projects/<project_id>/producer-package/ as Producer Studio's
    analog of the Production Package. Only called once Asset Validation has
    actually passed (ProducerStudioController's job to decide, not this
    writer's) - a failed validation run is never exported as a package."""
    package_dir = settings.OUTPUT_DIR / "projects" / project_id / "producer-package"
    package_dir.mkdir(parents=True, exist_ok=True)

    (package_dir / "asset_manifest.json").write_text(asset_manifest.model_dump_json(indent=2))

    files = [{"name": "asset_manifest.json", "description": MANIFEST_DESCRIPTIONS["asset_manifest.json"], "status": "generated"}]

    if timeline is not None:
        (package_dir / "timeline_plan.json").write_text(timeline.model_dump_json(indent=2))
        files.append({"name": "timeline_plan.json", "description": MANIFEST_DESCRIPTIONS["timeline_plan.json"], "status": "generated"})

    if subtitle_plan is not None:
        (package_dir / "subtitle_plan.json").write_text(subtitle_plan.model_dump_json(indent=2))
        files.append({"name": "subtitle_plan.json", "description": MANIFEST_DESCRIPTIONS["subtitle_plan.json"], "status": "generated"})

    if music_plan is not None:
        (package_dir / "music_plan.json").write_text(music_plan.model_dump_json(indent=2))
        files.append({"name": "music_plan.json", "description": MANIFEST_DESCRIPTIONS["music_plan.json"], "status": "generated"})

    if editing_plan is not None:
        (package_dir / "editing_plan.json").write_text(editing_plan.model_dump_json(indent=2))
        files.append({"name": "editing_plan.json", "description": MANIFEST_DESCRIPTIONS["editing_plan.json"], "status": "generated"})

    if thumbnail_plan is not None:
        (package_dir / "thumbnail_plan.json").write_text(thumbnail_plan.model_dump_json(indent=2))
        files.append({"name": "thumbnail_plan.json", "description": MANIFEST_DESCRIPTIONS["thumbnail_plan.json"], "status": "generated"})

    if publishing_plan is not None:
        (package_dir / "publishing_metadata.json").write_text(publishing_plan.model_dump_json(indent=2))
        files.append({"name": "publishing_metadata.json", "description": MANIFEST_DESCRIPTIONS["publishing_metadata.json"], "status": "generated"})

    manifest = {"package_id": project_id, "files": files}
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return package_dir

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from agents.asset_validator.contract import (
    AssetValidatorInput,
    ScannedMediaFile,
    ValidatedAsset,
    ValidatedAssetManifest,
    ValidationIssue,
)

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
VIDEO_EXTENSIONS = {"mp4", "mov"}
AUDIO_EXTENSIONS = {"wav", "mp3", "m4a"}

# Heuristic corruption floors, same convention as agents/image_generator/validator.py's
# MIN_VALID_IMAGE_BYTES - a file that exists but is implausibly small is treated as
# unusable rather than present, since neither this agent nor any other in Producer
# Studio actually decodes media content (ARCHITECTURE.md SS6: only FFmpeg Export is
# sanctioned to do real media I/O).
MIN_IMAGE_BYTES = 5_000
MIN_VIDEO_BYTES = 10_000
MIN_AUDIO_BYTES = 5_000

# Naming convention this milestone establishes for human-imported, per-shot media
# (nothing in ARCHITECTURE.md specified one yet): scene_<scene_id>_shot_<shot_id>.<ext>
# for images/video, and a single voice_script.<ext> for the whole project's narration,
# matching Prompt Intelligence's per-shot image_prompts.json/video_prompts.json
# granularity and Voice Script's single voice_script.txt output.
SHOT_FILENAME_RE = re.compile(r"^scene_(\d+)_shot_(\d+)\.([A-Za-z0-9]+)$")
NARRATION_FILENAME_RE = re.compile(r"^voice_script\.([A-Za-z0-9]+)$")


def _parse_shot_filename(filename: str) -> Optional[Tuple[int, int, str]]:
    match = SHOT_FILENAME_RE.match(filename)
    if not match:
        return None
    scene_id, shot_id, ext = match.groups()
    return int(scene_id), int(shot_id), ext.lower()


def _index_shots_by_slot(
    files: List[ScannedMediaFile], allowed_extensions: set, min_bytes: int, issues: List[ValidationIssue], kind: str
) -> Dict[Tuple[int, int], ScannedMediaFile]:
    """Groups scanned files by (scene_id, shot_id), reporting naming violations for
    filenames that don't match the convention and duplicate issues for any slot with
    more than one candidate file. Undersized files are treated as absent, not present -
    a corrupt/truncated file doesn't count as coverage."""
    by_slot: Dict[Tuple[int, int], List[ScannedMediaFile]] = defaultdict(list)

    for f in files:
        parsed = _parse_shot_filename(f.filename)
        if parsed is None:
            issues.append(ValidationIssue(
                category="naming",
                description=f"{kind} file '{f.filename}' doesn't match the required "
                            f"'scene_<id>_shot_<id>.<ext>' naming convention",
            ))
            continue

        scene_id, shot_id, ext = parsed
        if ext not in allowed_extensions:
            issues.append(ValidationIssue(
                category="naming",
                description=f"{kind} file '{f.filename}' has an unsupported extension "
                            f"'.{ext}' (allowed: {sorted(allowed_extensions)})",
            ))
            continue

        if f.size_bytes < min_bytes:
            issues.append(ValidationIssue(
                category="missing",
                description=f"{kind} file '{f.filename}' for scene {scene_id} shot {shot_id} "
                            f"is only {f.size_bytes} bytes - likely corrupt or truncated, treated as absent",
            ))
            continue

        by_slot[(scene_id, shot_id)].append(f)

    resolved: Dict[Tuple[int, int], ScannedMediaFile] = {}
    for slot, candidates in by_slot.items():
        if len(candidates) > 1:
            names = ", ".join(sorted(c.filename for c in candidates))
            issues.append(ValidationIssue(
                category="duplicate",
                description=f"Scene {slot[0]} shot {slot[1]} has {len(candidates)} candidate "
                            f"{kind.lower()} files ({names}) - ambiguous which one is canonical",
            ))
        resolved[slot] = candidates[0]

    return resolved


def _find_cross_slot_duplicates(*file_groups: List[ScannedMediaFile]) -> List[ValidationIssue]:
    """Detects the same file content (by hash) reused across different filenames -
    e.g. accidentally copy-pasting one shot's image as another's."""
    by_hash: Dict[str, List[ScannedMediaFile]] = defaultdict(list)
    for group in file_groups:
        for f in group:
            by_hash[f.sha256].append(f)

    issues = []
    for file_hash, files in by_hash.items():
        distinct_names = {f.filename for f in files}
        if len(distinct_names) > 1:
            names = ", ".join(sorted(distinct_names))
            issues.append(ValidationIssue(
                category="duplicate",
                description=f"Identical file content found under multiple names ({names}) - "
                            f"likely the same asset copy-pasted for more than one shot",
            ))
    return issues


def _resolve_narration(audio_files: List[ScannedMediaFile], issues: List[ValidationIssue]) -> Optional[str]:
    candidates = []
    for f in audio_files:
        match = NARRATION_FILENAME_RE.match(f.filename)
        if not match:
            issues.append(ValidationIssue(
                category="naming",
                description=f"Audio file '{f.filename}' doesn't match the required "
                            f"'voice_script.<ext>' naming convention",
            ))
            continue

        ext = match.group(1).lower()
        if ext not in AUDIO_EXTENSIONS:
            issues.append(ValidationIssue(
                category="naming",
                description=f"Narration file '{f.filename}' has an unsupported extension "
                            f"'.{ext}' (allowed: {sorted(AUDIO_EXTENSIONS)})",
            ))
            continue

        if f.size_bytes < MIN_AUDIO_BYTES:
            issues.append(ValidationIssue(
                category="missing",
                description=f"Narration file '{f.filename}' is only {f.size_bytes} bytes - "
                            f"likely corrupt or truncated, treated as absent",
            ))
            continue

        candidates.append(f)

    if not candidates:
        issues.append(ValidationIssue(category="narration", description="No valid narration audio file found"))
        return None

    if len(candidates) > 1:
        names = ", ".join(sorted(c.filename for c in candidates))
        issues.append(ValidationIssue(
            category="duplicate",
            description=f"Found {len(candidates)} candidate narration files ({names}) - "
                        f"ambiguous which one is canonical",
        ))

    return candidates[0].path


def validate_assets(input_data: AssetValidatorInput) -> ValidatedAssetManifest:
    """Confirms imported media covers every shot Prompt Intelligence produced prompts
    for, plus narration audio - the entry gate before any further Producer Studio
    planning proceeds (ARCHITECTURE.md SS6). Unlike other agents' validators, an
    incomplete result is not an exception: a human's media/ folder being unfinished
    is an expected, reportable outcome, not a bug - it's surfaced via `issues` and
    `is_valid=False` so ProducerStudioController can decline to advance project state
    without treating this as a crash."""
    issues: List[ValidationIssue] = []

    image_slots = _index_shots_by_slot(
        input_data.imported_media.images, IMAGE_EXTENSIONS, MIN_IMAGE_BYTES, issues, "Image"
    )
    video_slots = _index_shots_by_slot(
        input_data.imported_media.videos, VIDEO_EXTENSIONS, MIN_VIDEO_BYTES, issues, "Video"
    )
    issues.extend(_find_cross_slot_duplicates(list(image_slots.values()), list(video_slots.values())))

    assets: List[ValidatedAsset] = []
    for shot in input_data.prompt_set.shots:
        slot = (shot.scene_id, shot.shot_id)
        image_file = image_slots.get(slot)
        video_file = video_slots.get(slot)

        if image_file is None and video_file is None:
            issues.append(ValidationIssue(
                category="missing",
                description=f"Scene {shot.scene_id} shot {shot.shot_id} has no image or video asset",
            ))

        assets.append(ValidatedAsset(
            scene_id=shot.scene_id,
            shot_id=shot.shot_id,
            image_path=image_file.path if image_file else None,
            video_path=video_file.path if video_file else None,
        ))

    narration_audio_path = _resolve_narration(input_data.imported_media.audio, issues)

    is_valid = len(issues) == 0

    return ValidatedAssetManifest(
        source_prompt_set_id=input_data.prompt_set.prompt_set_id,
        assets=assets,
        narration_audio_path=narration_audio_path,
        issues=issues,
        is_valid=is_valid,
    )

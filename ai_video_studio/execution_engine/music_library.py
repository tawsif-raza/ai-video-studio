"""
Local royalty-free music library resolution (ARCHITECTURE.md SS7, SS21 item 9,
SS23 "Audio mixing") - the asset source Music Planning's already-computed
mood/tempo/intensity/fade/ducking strategy had nothing to mix against until
now. Mirrors the split video_generation_engine/provider_registry.py and
publishing_engine/platforms/registry.py already establish for "resolve typed
plan data against a small local catalog": a boundary loader reads the on-disk
index, a pure function matches an already-loaded index against a MusicPlan,
and a second boundary function re-confirms the resolved path exists
immediately before render (called from preflight.py) - the same "planning
approved it, but media I/O is real" justification preflight.py's own
verify_media_exists docstring already gives for every other planned asset.

No match is ever fatal here: an unmatched MusicPlan, an empty library, or a
missing/malformed index all resolve to None, and command_builder falls back
to today's narration-only passthrough - mirroring ffmpeg_detector's "report
availability as data, never raise" convention. The one case that DOES raise
is a resolved-but-then-vanished path, exactly like any other missing media
asset (§21 item 9's "graceful degrade for no-match, not for a real integrity
problem" distinction) - that raise lives in preflight.py, not here.

MusicLibraryEntry is new supporting data for this module's own matching, not
a Producer Package contract - no project ever carries one of these, and
MusicPlan itself (shared_core/contracts/music_plan.py) is unmodified.
"""

import json
import os
from typing import List, Optional

from pydantic import BaseModel

from shared_core.contracts.music_plan import MusicCue, MusicPlan

# assets/music/ sits at the package root, alongside outputs/ - resolved
# relative to this file (not via config.py: execution_engine/ imports only
# shared_core.contracts and project_manager, per ARCHITECTURE.md SS7/SS19,
# and config.py is neither).
DEFAULT_LIBRARY_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "music")
)
DEFAULT_LIBRARY_INDEX_PATH = os.path.join(DEFAULT_LIBRARY_DIR, "library_index.json")


class MusicLibraryEntry(BaseModel):
    """One track in the local royalty-free library, as read from
    library_index.json. `path` is stored relative to the index file's own
    directory (so the index stays portable if assets/music/ ever moves) and
    resolved to an absolute path by load_library_index - resolve_music_asset
    itself never touches the filesystem, so it always sees an already-usable
    path."""

    path: str
    mood: str
    tempo: str
    intensity: str = "medium"
    label: Optional[str] = None


def load_library_index(index_path: str = DEFAULT_LIBRARY_INDEX_PATH) -> List[MusicLibraryEntry]:
    """Boundary: the module's one real filesystem read. Never raises - a
    missing, empty, or malformed index (or a malformed individual entry)
    reports as an empty (or partial) library rather than crashing the
    render, the same "report as data" convention ffmpeg_detector.
    detect_ffmpeg already establishes for a missing binary. This is exactly
    the placeholder state Milestone A ships with: no real tracks sourced
    yet means every render simply resolves no music and falls back to
    narration-only, not a broken pipeline."""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    tracks = raw.get("tracks", []) if isinstance(raw, dict) else []
    base_dir = os.path.dirname(os.path.abspath(index_path))

    entries: List[MusicLibraryEntry] = []
    for item in tracks:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        resolved = dict(item)
        if not os.path.isabs(resolved["path"]):
            resolved["path"] = os.path.normpath(os.path.join(base_dir, resolved["path"]))
        try:
            entries.append(MusicLibraryEntry(**resolved))
        except Exception:
            continue
    return entries


def _representative_cue(music_plan: MusicPlan) -> Optional[MusicCue]:
    """Milestone A mixes ONE continuous music bed for the whole video (see
    command_builder's single music `-i` input, and filter_graph_builder.
    build_audio_filter_graph), not a per-scene track switch - so one cue
    has to stand in for "the video's music" when matching against the
    library. The first non-silent cue is the simplest deterministic choice
    that's actually representative of what a viewer hears first; a
    majority-mood vote across cues is a reasonable future refinement but
    not needed for this foundation milestone. None (every cue silent, or
    no cues at all) means the plan calls for no music at all."""
    for cue in music_plan.cues:
        if not cue.is_silent:
            return cue
    return None


def resolve_music_asset(music_plan: MusicPlan, library: List[MusicLibraryEntry]) -> Optional[str]:
    """Pure: zero filesystem/subprocess calls - `library` is already-loaded
    data (load_library_index), so this is a typed function of typed inputs,
    exactly like filter_graph_builder's functions. Matches the plan's
    representative cue against the library most-specific-first
    (mood+tempo+intensity, then mood+tempo, then mood alone) and returns
    the first entry's path at whichever tier first has a hit. Returns None
    - never raises - when every cue is silent or nothing in the library
    matches at any tier; the caller (command_builder, via the controller)
    treats None as "no music for this render", not an error."""
    cue = _representative_cue(music_plan)
    if cue is None:
        return None

    for entry in library:
        if entry.mood == cue.mood and entry.tempo == cue.tempo and entry.intensity == cue.intensity:
            return entry.path
    for entry in library:
        if entry.mood == cue.mood and entry.tempo == cue.tempo:
            return entry.path
    for entry in library:
        if entry.mood == cue.mood:
            return entry.path
    return None


def verify_music_asset_exists(path: str) -> bool:
    """Boundary: real filesystem check, mirroring preflight.py's own
    os.path.isfile calls for shot/narration assets. Returns a bool rather
    than raising - preflight.py is the one place a False here becomes a
    MediaAccessError, since a resolved-but-missing path is a real
    integrity problem (the library index promised a file that isn't
    there), unlike an unmatched MusicPlan which is an expected, graceful
    "no music" outcome handled entirely by resolve_music_asset returning
    None."""
    return os.path.isfile(path)

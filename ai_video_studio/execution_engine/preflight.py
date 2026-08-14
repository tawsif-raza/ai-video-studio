"""
Media-existence preflight - the Execution Engine's one filesystem read at 8.1.
This belongs to the engine, not to Project Manager, because it is *media* I/O:
ARCHITECTURE.md SS6 sanctions the Execution Engine (and only it) to touch media
files, while Project Manager owns project/package persistence. Verifying that a
planned asset still exists on disk is the lightest form of that media access,
and it must happen here rather than trusting the manifest blindly, since a file
can move or be deleted between planning and rendering.

Also re-confirms a resolved music asset (ARCHITECTURE.md SS21 item 9) the same
way: request.music_asset_path was already matched against the library by
music_library.resolve_music_asset (called by the controller before this runs),
but that match is just a claim about the library index - the file itself can
still have moved or been deleted, same as any other planned asset. A resolved-
but-missing music path is treated with the same severity as a missing shot
asset (MediaAccessError), unlike an *unmatched* MusicPlan (music_asset_path is
None), which is never an error - see music_library's module docstring for that
"no match is a graceful degrade, a vanished match is a real problem"
distinction.
"""

import os

from execution_engine.errors import MediaAccessError
from execution_engine.music_library import verify_music_asset_exists
from shared_core.contracts.render import RenderRequest


def verify_media_exists(request: RenderRequest) -> None:
    """Confirms every editing segment's asset, the narration audio, and (if
    one was resolved) the music asset are present and readable as regular
    files. Raises MediaAccessError naming every missing path (not just the
    first), so a human fixing their media/ folder sees the full list at
    once."""
    missing = []

    for segment in request.editing_plan.segments:
        if segment.asset_type == "black":
            # Asset Validation tolerated this shot as missing - there is no
            # real file to check, command_builder synthesizes a black frame
            # for it instead.
            continue
        if not os.path.isfile(segment.asset_path):
            missing.append(segment.asset_path)

    narration_path = request.asset_manifest.narration_audio_path
    if narration_path and not os.path.isfile(narration_path):
        missing.append(narration_path)

    if request.music_asset_path and not verify_music_asset_exists(request.music_asset_path):
        missing.append(request.music_asset_path)

    if missing:
        raise MediaAccessError(
            "Missing media file(s) the editing plan depends on: " + ", ".join(missing)
        )

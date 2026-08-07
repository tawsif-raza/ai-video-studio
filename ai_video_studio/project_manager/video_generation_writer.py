# The Video Generation Engine's own writer, owned by Project Manager
# (ARCHITECTURE.md SS25.10), mirroring render_writer.py's convention: report
# shapes are defined once as typed schemas in shared_core/contracts, and this
# module only serializes an instance of one to disk.
#
# One file: video_manifest.json, inside the Production Package, alongside the
# already-existing video_prompts.json. Holds the VideoGenerationManifest's
# cumulative selections/assets/results/validation_reports across every
# attempted (non-dry-run) generation run for a project - ProjectManager merges
# a new run's results into the existing manifest before calling this (see
# ProjectManager.save_video_generation_result), so this module itself is a
# pure "serialize the given instance" step, same division of labor
# render_writer.py has with ProjectManager.save_render_result.
#
# The clip files themselves are written directly by the provider adapter
# (e.g. providers/stub.py), not here - this module only ever writes the one
# JSON manifest alongside them.

from pathlib import Path

from shared_core.contracts.video_generation import VideoGenerationManifest

MANIFEST_FILENAME = "video_manifest.json"


def write_video_generation_manifest(
    *, production_package_dir: str, manifest: VideoGenerationManifest
) -> Path:
    package_dir = Path(production_package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = package_dir / MANIFEST_FILENAME
    manifest_path.write_text(manifest.model_dump_json(indent=2))
    return manifest_path

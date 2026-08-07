"""
Media/output-directory preflight - the Video Generation Engine's one real
filesystem check before generation is attempted (ARCHITECTURE.md SS25.6).
Boundary (read-only plus a throwaway write probe): confirms the target
media/video/ output directory is actually writable and that a given
seed_image_path (image-to-video conditioning, SS25.4) still exists on disk -
planning-time approval (a valid ShotMediaSelection) is not the same
guarantee as real I/O being possible right now.

Does not separately re-check that the requested shot has a
video_motion_prompt: by the time a VideoGenerationRequest exists,
request_builder.resolve_selected_shots has already matched it against a real
PromptSet entry, and ShotPromptSchema's own min_length=15 constraint
(shared_core/contracts/prompt_set.py) makes an empty video_motion_prompt
structurally impossible - there is nothing left here to verify that
Pydantic validation and request_builder haven't already guaranteed.
"""

from pathlib import Path

from shared_core.contracts.video_generation import VideoGenerationRequest
from video_generation_engine.errors import MediaAccessError

_WRITE_PROBE_FILENAME = ".vge_write_check"


def verify_generation_inputs(request: VideoGenerationRequest) -> None:
    """Raises MediaAccessError naming every problem found, not just the
    first - the same convention execution_engine.preflight.verify_media_exists
    already established."""
    problems = []

    seed_path = request.options.seed_image_path
    if seed_path and not Path(seed_path).is_file():
        problems.append(f"seed image not found: {seed_path}")

    output_dir = Path(request.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe_file = output_dir / _WRITE_PROBE_FILENAME
        probe_file.write_bytes(b"")
        probe_file.unlink(missing_ok=True)
    except OSError as exc:
        problems.append(f"output directory '{output_dir}' is not writable: {exc}")

    if problems:
        raise MediaAccessError("; ".join(problems))

"""
Pure resolver/assembler of typed generation requests (ARCHITECTURE.md
SS25.6). Resolves ShotMediaSelection entries against the loaded PromptSet and
assembles the typed VideoGenerationRequest per selected shot. No filesystem
access beyond what it's handed, no subprocess, no provider call - a typed
function of typed data to typed data, exactly like execution_engine's
command_builder.
"""

from typing import List

from shared_core.contracts.prompt_set import PromptSet, ShotPrompt
from shared_core.contracts.video_generation import ShotMediaSelection, VideoGenerationOptions, VideoGenerationRequest
from video_generation_engine.errors import VideoGenerationInputError


def resolve_selected_shots(prompt_set: PromptSet, selections: List[ShotMediaSelection]) -> List[ShotPrompt]:
    """Resolves every "video"-mode selection against prompt_set.shots, in
    selection order; "image"-mode selections are skipped entirely (today's
    default behavior, SS25.3). Raises VideoGenerationInputError naming every
    selection that doesn't match a shot in the prompt set, not just the
    first - the same "name every problem, not just the first" convention
    execution_engine.preflight.verify_media_exists already established."""
    by_key = {(sp.scene_id, sp.shot_id): sp for sp in prompt_set.shots}
    resolved: List[ShotPrompt] = []
    missing: List[str] = []
    for selection in selections:
        if selection.mode != "video":
            continue
        shot_prompt = by_key.get((selection.scene_id, selection.shot_id))
        if shot_prompt is None:
            missing.append(f"scene {selection.scene_id} shot {selection.shot_id}")
            continue
        resolved.append(shot_prompt)

    if missing:
        raise VideoGenerationInputError(
            "ShotMediaSelection references shot(s) not present in the prompt set: " + ", ".join(missing)
        )
    return resolved


def build_generation_request(
    shot_prompt: ShotPrompt, *, output_dir: str, options: VideoGenerationOptions
) -> VideoGenerationRequest:
    """Assembles one shot's typed VideoGenerationRequest. scene_id/shot_id
    are copied straight from shot_prompt - the only source of truth for
    them - so the request can never disagree with its own shot_prompt at
    construction time (validate_generation_request re-confirms this for a
    request built any other way, e.g. directly in a test)."""
    return VideoGenerationRequest(
        shot_prompt=shot_prompt,
        scene_id=shot_prompt.scene_id,
        shot_id=shot_prompt.shot_id,
        output_dir=output_dir,
        options=options,
    )


def validate_generation_request(request: VideoGenerationRequest) -> None:
    """Confirms the request is internally consistent and complete enough to
    attempt generation. Raises VideoGenerationInputError on the first
    problem found."""
    if request.scene_id != request.shot_prompt.scene_id or request.shot_id != request.shot_prompt.shot_id:
        raise VideoGenerationInputError(
            f"VideoGenerationRequest scene/shot ({request.scene_id}, {request.shot_id}) does not match "
            f"its own shot_prompt ({request.shot_prompt.scene_id}, {request.shot_prompt.shot_id})"
        )
    if not request.output_dir:
        raise VideoGenerationInputError("VideoGenerationRequest.output_dir must be set")

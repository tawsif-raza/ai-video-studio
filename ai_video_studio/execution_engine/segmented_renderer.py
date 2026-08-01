"""
Fallback render strategy for editing plans with many scene-crossfade
boundaries. The default path (command_builder + filter_graph_builder) holds
every visual input open in one ffmpeg process via a single filter_complex -
production telemetry showed this can exceed a constrained deployment's
memory ceiling well before output resolution is the limiting factor: a
21-shot/9-scene render peaked at ~830-860MB regardless of 1080p vs 720p
output, and was SIGKILLed on a 1GB container. This module trades some
wall-clock time and one extra re-encode per scene boundary for a hard cap
on how many real ffmpeg inputs are ever open at once, independent of the
edit's total shot count:

1. Segments are grouped into 'cut' chains (filter_graph_builder.
   group_into_chains) - each chain has no internal crossfades, so it's
   rendered by its own small ffmpeg process (as many -i inputs as that one
   chain has, never the whole edit's).
2. Chains are then merged pairwise, left to right, via a 2-input xfade per
   step - each step reads two already-rendered files, never more, so peak
   memory per step does not grow with how many chains preceded it.
3. The fully-merged, video-only result is muxed with the narration audio in
   one final, cheap (`-c:v copy`) step to produce the real output file.

Every step still goes through the same ffmpeg_executor.execute() boundary
and is an ordinary FFmpegCommandSpec - this module only decides how many
processes to run and what each one contains. Every duration/offset/
transition value is read from the same EditingPlan the single-pass path
also reads; no content decision is made here (ARCHITECTURE.md SS7: the
Execution Engine invents no content).
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from execution_engine.command_builder import build_segment_input
from execution_engine.errors import RenderInputError
from execution_engine.ffmpeg_executor import execute
from execution_engine.ffmpeg_format import format_seconds
from execution_engine.filter_graph_builder import (
    CROSSFADE_SECONDS,
    build_segment_chain,
    group_into_chains,
    parse_resolution,
    segment_duration,
    validate_boundary_transitions,
)
from shared_core.contracts.editing_plan import EditingSegment
from shared_core.contracts.render import FFmpegCommandSpec, FFmpegInput, RenderOptions, RenderRequest, RenderResult
from utils.logger import get_logger

logger = get_logger("execution_engine.segmented_renderer")

# Chain count (scene-crossfade boundaries) above which the single
# filter_complex path is skipped in favor of this module's disk-based,
# bounded-memory pipeline. Chosen empirically: comfortably above every
# single-scene/simple-multi-scene fixture already covered by this repo's
# tests (so the existing, cheaper single-pass path stays untouched for
# typical small projects) and comfortably below the 9-chain project
# observed to OOM this deployment.
SEGMENT_CHAIN_THRESHOLD = 3

GLOBAL_ARGS = ["-y", "-hide_banner", "-loglevel", "error"]


def should_segment(editing_plan) -> bool:
    """True when the edit has enough scene-crossfade boundaries that
    building it as one filter_complex risks the memory ceiling this
    fallback exists for. Reuses group_into_chains's own boundary detection,
    so this decision always agrees with whatever the single-pass path would
    have compiled from the same plan."""
    chains = group_into_chains(editing_plan.segments)
    return len(chains) > SEGMENT_CHAIN_THRESHOLD


@dataclass(frozen=True)
class RenderStep:
    """One ffmpeg invocation in the segmented pipeline, plus a short label
    for logging - segmented_renderer's unit of work."""

    command_spec: FFmpegCommandSpec
    description: str


def _chain_output_args(options: RenderOptions) -> List[str]:
    """Video-only intermediate output - narration audio is added only in
    the final mux step, never per-chain/per-merge, so no intermediate
    re-encode ever touches audio."""
    return [
        "-an",
        "-c:v", options.video_codec,
        "-preset", options.preset,
        "-crf", str(options.crf),
        "-threads", str(options.threads),
        "-pix_fmt", options.pix_fmt,
        "-r", str(options.fps),
    ]


def _build_chain_step(
    chain: List[int],
    segments: List[EditingSegment],
    *,
    global_first_index: int,
    global_last_index: int,
    options: RenderOptions,
    output_path: Path,
) -> RenderStep:
    """One chain's own small filter_complex (trim/normalize + concat if more
    than one segment) - at most as many -i inputs as this one chain has,
    never the whole edit's. is_first/is_last are evaluated against the
    segment's position in the WHOLE edit (matching filter_graph_builder's
    own single-pass semantics for where the opening/closing fade-from/to-
    black belongs), not its position within this chain."""
    width, height = parse_resolution(options.resolution)
    inputs = [build_segment_input(segments[idx], options.resolution) for idx in chain]

    filters: List[str] = []
    local_labels: List[str] = []
    for local_index, global_index in enumerate(chain):
        seg_filters, label = build_segment_chain(
            local_index,
            segments[global_index],
            is_first=(global_index == global_first_index),
            is_last=(global_index == global_last_index),
            width=width,
            height=height,
            fps=options.fps,
        )
        filters.extend(seg_filters)
        local_labels.append(label)

    if len(local_labels) == 1:
        video_label = local_labels[0]
    else:
        concat_inputs = "".join(f"[{lbl}]" for lbl in local_labels)
        video_label = "chain_out"
        filters.append(f"{concat_inputs}concat=n={len(local_labels)}:v=1:a=0,fps={options.fps}[{video_label}]")

    output_args = ["-map", f"[{video_label}]", *_chain_output_args(options)]

    spec = FFmpegCommandSpec(
        global_args=list(GLOBAL_ARGS),
        inputs=inputs,
        filter_complex=";".join(filters),
        output_args=output_args,
        output_path=str(output_path),
    )
    return RenderStep(command_spec=spec, description=f"chain render ({len(chain)} shot(s)) -> {output_path.name}")


def _build_merge_step(
    accumulated_path: Path,
    next_path: Path,
    *,
    xfade_duration: float,
    offset: float,
    options: RenderOptions,
    output_path: Path,
) -> RenderStep:
    """Crossfades two already-rendered video-only files together - exactly
    two real inputs, regardless of how many chains preceded this step or
    how far into the timeline `offset` falls, since both inputs are
    ordinary video files ffmpeg streams from disk rather than live decoder
    branches held open in one shared graph."""
    inputs = [
        FFmpegInput(path=str(accumulated_path), kind="video"),
        FFmpegInput(path=str(next_path), kind="video"),
    ]
    filter_complex = (
        f"[0:v][1:v]xfade=transition=fade:duration={format_seconds(xfade_duration)}:"
        f"offset={format_seconds(offset)}[merged]"
    )
    output_args = ["-map", "[merged]", *_chain_output_args(options)]
    spec = FFmpegCommandSpec(
        global_args=list(GLOBAL_ARGS),
        inputs=inputs,
        filter_complex=filter_complex,
        output_args=output_args,
        output_path=str(output_path),
    )
    return RenderStep(command_spec=spec, description=f"merge -> {output_path.name}")


def _build_final_mux_step(
    video_only_path: Path, narration_audio_path: str, options: RenderOptions, output_path: Path,
) -> RenderStep:
    """Combines the fully-merged, video-only timeline with the narration
    audio - the one step in this pipeline that produces the real, final
    output. `-c:v copy` is safe here: video_only_path was already encoded
    at the render's final codec/crf/preset/pix_fmt/fps by the last chain or
    merge step, so nothing about picture quality changes by copying it
    instead of re-encoding yet again."""
    inputs = [
        FFmpegInput(path=str(video_only_path), kind="video"),
        FFmpegInput(path=narration_audio_path, kind="audio"),
    ]
    output_args = [
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", options.audio_codec,
    ]
    spec = FFmpegCommandSpec(
        global_args=list(GLOBAL_ARGS),
        inputs=inputs,
        filter_complex=None,
        output_args=output_args,
        output_path=str(output_path),
    )
    return RenderStep(command_spec=spec, description=f"final audio mux -> {output_path.name}")


def build_segmented_render_plan(request: RenderRequest, segment_dir: Path) -> List[RenderStep]:
    """Pure: given an already-validated RenderRequest (validate_render_request
    / verify_media_exists have already run - this function trusts that,
    exactly like command_builder.build_command does) and the directory
    intermediate files should live under, returns the ordered list of
    RenderSteps execute_segmented will run. No filesystem access, no
    subprocess - segment_dir is only ever used to compute path strings."""
    options = request.options
    segments = request.editing_plan.segments
    if not segments:
        raise RenderInputError("Editing plan has no segments - nothing to render")
    validate_boundary_transitions(segments)

    chains = group_into_chains(segments)
    global_first_index = 0
    global_last_index = len(segments) - 1

    steps: List[RenderStep] = []
    chain_paths: List[Path] = []
    chain_durations: List[float] = []
    for i, chain in enumerate(chains):
        output_path = segment_dir / f"chain_{i}.mp4"
        steps.append(_build_chain_step(
            chain, segments,
            global_first_index=global_first_index, global_last_index=global_last_index,
            options=options, output_path=output_path,
        ))
        chain_paths.append(output_path)
        chain_durations.append(sum(segment_duration(segments[idx]) for idx in chain))

    accumulated_path = chain_paths[0]
    accumulated_duration = chain_durations[0]
    for i in range(1, len(chains)):
        next_path = chain_paths[i]
        next_duration = chain_durations[i]
        xfade_duration = min(CROSSFADE_SECONDS, accumulated_duration / 2, next_duration / 2)
        offset = max(accumulated_duration - xfade_duration, 0)
        merged_path = segment_dir / f"merge_{i}.mp4"
        steps.append(_build_merge_step(
            accumulated_path, next_path,
            xfade_duration=xfade_duration, offset=offset,
            options=options, output_path=merged_path,
        ))
        accumulated_path = merged_path
        accumulated_duration = accumulated_duration + next_duration - xfade_duration

    final_output_path = Path(request.output_dir) / "video.mp4"
    steps.append(_build_final_mux_step(
        accumulated_path, request.asset_manifest.narration_audio_path, options, final_output_path,
    ))
    return steps


def execute_segmented(
    request: RenderRequest,
    *,
    ffmpeg_path: str = "ffmpeg",
    timeout_seconds: Optional[int] = None,
    executor=execute,
) -> RenderResult:
    """Runs build_segmented_render_plan's steps in order through the same
    ffmpeg_executor.execute() the single-pass path uses - every step is an
    ordinary FFmpegCommandSpec, so atomic-write and failure-reporting
    behavior is identical to a normal render, just repeated per step. Stops
    at the first failing step and returns its RenderResult (a failed
    intermediate step is exactly as reportable as a failed single-pass
    render). On overall success, cleans up every intermediate file and
    returns the final step's RenderResult (output_path is the real final
    video) with duration_seconds replaced by the SUM of every step's
    wall-clock time, since that's what actually elapsed even though it's
    spread across several subprocess calls instead of one."""
    segment_dir = Path(request.output_dir) / ".segments"
    segment_dir.mkdir(parents=True, exist_ok=True)

    steps = build_segmented_render_plan(request, segment_dir)
    logger.info(f"Segmented render: {len(steps)} step(s) in {segment_dir}")

    total_duration = 0.0
    started_at = None
    result: Optional[RenderResult] = None
    for step in steps:
        logger.info(f"Segmented render step: {step.description}")
        result = executor(step.command_spec, ffmpeg_path=ffmpeg_path, timeout_seconds=timeout_seconds)
        if started_at is None:
            started_at = result.started_at
        total_duration += result.duration_seconds or 0.0
        if not result.success:
            logger.error(f"Segmented render step failed ({step.description}): {result.error}")
            _cleanup_dir(segment_dir)
            return result.model_copy(update={"duration_seconds": total_duration, "started_at": started_at})

    logger.info(f"Segmented render succeeded across {len(steps)} step(s), {total_duration:.1f}s total")
    _cleanup_dir(segment_dir)
    return result.model_copy(update={"duration_seconds": total_duration, "started_at": started_at})


def _cleanup_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)

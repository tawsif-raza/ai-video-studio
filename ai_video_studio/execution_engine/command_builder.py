"""
Pure translation of a validated RenderRequest into an FFmpegCommandSpec - the
command_builder in the Execution Engine's architecture. No filesystem access,
no subprocess, no ffmpeg: given typed contracts, it returns a typed command
object. This is the compiler, not the renderer, and it is what keeps the engine
on the right side of the 'never performs planning' rule - every ordering,
duration, and transition decision was already made and is merely transcribed.

Milestone 8.1 built the inputs list, global args, and output configuration
with filter_complex left as None. Milestone 8.2 fills filter_complex in by
delegating to the dedicated filter_graph_builder component (cut/fade/xfade
plus resolution/fps normalization) and adds the -map arguments the compiled
graph requires. Audio mixing and subtitle burn-in remain deferred: the
narration audio input is still mapped straight through, unfiltered.
"""

from pathlib import Path

from execution_engine.errors import RenderInputError
from execution_engine.ffmpeg_format import format_seconds
from execution_engine.filter_graph_builder import build_visual_filter_graph, parse_resolution
from shared_core.contracts.render import FFmpegCommandSpec, FFmpegInput, RenderOptions, RenderRequest

GLOBAL_ARGS = ["-y", "-hide_banner", "-loglevel", "error"]
OUTPUT_FILENAME = "video.mp4"


def validate_render_request(request: RenderRequest) -> None:
    """Confirms the Producer Package inputs are present, valid, and mutually
    consistent before any command is built. Raises RenderInputError on the
    first problem found. This is the provenance chain the Editing Planner
    established, re-checked at the execution boundary: every artifact must
    descend from the same timeline and asset manifest, or the render would
    weld together plans from different runs."""
    editing_plan = request.editing_plan
    manifest = request.asset_manifest
    timeline = request.timeline
    subtitle_plan = request.subtitle_plan
    music_plan = request.music_plan

    if not editing_plan.segments:
        raise RenderInputError("Editing plan has no segments - nothing to render")

    if not manifest.is_valid:
        raise RenderInputError(
            f"Asset manifest {manifest.manifest_id} did not pass validation (is_valid=False)"
        )

    if not manifest.narration_audio_path:
        raise RenderInputError(
            f"Asset manifest {manifest.manifest_id} has no narration audio path"
        )

    if timeline.source_asset_manifest_id != manifest.manifest_id:
        raise RenderInputError(
            f"Timeline {timeline.timeline_id} was built from asset manifest "
            f"{timeline.source_asset_manifest_id}, not the provided manifest {manifest.manifest_id}"
        )
    if editing_plan.source_timeline_id != timeline.timeline_id:
        raise RenderInputError(
            f"Editing plan {editing_plan.editing_plan_id} was built from timeline "
            f"{editing_plan.source_timeline_id}, not the provided timeline {timeline.timeline_id}"
        )
    if subtitle_plan.source_timeline_id != timeline.timeline_id:
        raise RenderInputError(
            f"Subtitle plan {subtitle_plan.subtitle_plan_id} was built from timeline "
            f"{subtitle_plan.source_timeline_id}, not the provided timeline {timeline.timeline_id}"
        )
    if music_plan.source_timeline_id != timeline.timeline_id:
        raise RenderInputError(
            f"Music plan {music_plan.music_plan_id} was built from timeline "
            f"{music_plan.source_timeline_id}, not the provided timeline {timeline.timeline_id}"
        )
    if editing_plan.source_subtitle_plan_id != subtitle_plan.subtitle_plan_id:
        raise RenderInputError(
            f"Editing plan references subtitle plan {editing_plan.source_subtitle_plan_id}, "
            f"not the provided {subtitle_plan.subtitle_plan_id}"
        )
    if editing_plan.source_music_plan_id != music_plan.music_plan_id:
        raise RenderInputError(
            f"Editing plan references music plan {editing_plan.source_music_plan_id}, "
            f"not the provided {music_plan.music_plan_id}"
        )

    for segment in editing_plan.segments:
        if segment.end_time <= segment.start_time:
            raise RenderInputError(
                f"Editing segment scene {segment.scene_id} shot {segment.shot_id} has a "
                f"non-positive duration ({segment.start_time} -> {segment.end_time})"
            )


def _output_args(options: RenderOptions) -> list:
    """Render configuration, as output-stage ffmpeg args. Overall output
    resolution is not set here (e.g. via -s): the filter graph already scales
    every input to the target frame, so the encoder just receives frames
    already at that size. fps is set for the same reason it's also normalized
    in the graph - belt and suspenders for a value the graph already fixed."""
    return [
        "-c:v", options.video_codec,
        "-preset", options.preset,
        "-crf", str(options.crf),
        "-threads", str(options.threads),
        "-c:a", options.audio_codec,
        "-pix_fmt", options.pix_fmt,
        "-r", str(options.fps),
    ]


def build_segment_input(segment, resolution: str) -> FFmpegInput:
    """Builds one editing segment's FFmpegInput - promoted out of
    build_command so segmented_renderer.py (execution_engine's fallback for
    high-memory many-scene projects, see its module docstring) can build
    the exact same per-chain inputs without duplicating the image-loop/
    black-frame-synthesis logic.

    Images carry `-loop 1 -t <dur>` so a still becomes a finite clip; a video
    input is trimmed to the plan's duration inside the filter graph instead
    (filter_graph_builder), since that requires a filter operating on decoded
    frames, not a pre-input flag. A "black" segment (a shot Asset Validation
    tolerated as missing, up to MAX_TOLERATED_MISSING_SHOTS) has no real file
    at all - it becomes an `-f lavfi -i color=c=black:s=<w>x<h>:d=<dur>`
    synthetic input sized to this render's own resolution, the one place a
    concrete WxH is chosen for it (Timeline/Editing Planning deliberately
    only carry the fact that it's missing, not a resolution, since that's a
    per-render decision)."""
    duration = segment.end_time - segment.start_time
    if segment.asset_type == "image":
        pre_input_args = ["-loop", "1", "-t", format_seconds(duration)]
        input_path = segment.asset_path
    elif segment.asset_type == "black":
        width, height = parse_resolution(resolution)
        pre_input_args = ["-f", "lavfi"]
        input_path = f"color=c=black:s={width}x{height}:d={format_seconds(duration)}"
    else:
        pre_input_args = []
        input_path = segment.asset_path
    return FFmpegInput(
        path=input_path,
        kind=segment.asset_type,
        scene_id=segment.scene_id,
        shot_id=segment.shot_id,
        duration_seconds=duration,
        pre_input_args=pre_input_args,
    )


def build_command(request: RenderRequest) -> FFmpegCommandSpec:
    """Builds the FFmpegCommandSpec from a request that has already been
    validated (validate_render_request) and whose media has been confirmed to
    exist (preflight.verify_media_exists). One visual input per editing
    segment, in plan order, then the single narration audio input last.

    The compiled visual graph's output stream is explicitly mapped alongside
    the raw (unfiltered) narration audio stream - audio mixing is still
    deferred, so the narration is only ever passed through, never blended."""
    inputs = [build_segment_input(segment, request.options.resolution) for segment in request.editing_plan.segments]

    inputs.append(FFmpegInput(
        path=request.asset_manifest.narration_audio_path,
        kind="audio",
    ))
    audio_input_index = len(inputs) - 1

    graph = build_visual_filter_graph(request.editing_plan, request.options)

    output_path = str(Path(request.output_dir) / OUTPUT_FILENAME)

    output_args = [
        "-map", f"[{graph.video_output_label}]",
        "-map", f"{audio_input_index}:a",
        *_output_args(request.options),
    ]

    return FFmpegCommandSpec(
        global_args=list(GLOBAL_ARGS),
        inputs=inputs,
        filter_complex=graph.filter_complex,
        output_args=output_args,
        output_path=output_path,
    )

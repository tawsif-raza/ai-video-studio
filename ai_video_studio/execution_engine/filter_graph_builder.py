"""
Pure builder for the visual timeline's ffmpeg filter_complex graph - the
dedicated filter_graph_builder component consumed by command_builder. Driven
solely by the Editing Plan: its segments already carry the exact per-shot
timing Timeline Planning computed, so no other Producer Package artifact is
needed here. Given only editing_plan and the render's resolution/fps options,
it deterministically compiles:

- resolution + fps normalization for every visual input (scale + letterbox
  pad + setsar + fps, so image and video inputs of any source size/rate/SAR
  join cleanly - concat and xfade both require matching formats)
- video duration conformance: a video segment is trimmed to the editing
  plan's duration (an image is already exactly that length via command_
  builder's `-loop 1 -t <dur>`, so it needs no trim here)
- hard cuts within a scene, via the `concat` filter
- crossfades at scene boundaries, via `xfade`
- fade-from-black at the very start and fade-to-black at the very end of the
  whole edit, via `fade`

No filesystem access, no subprocess, no execution - a typed function of typed
plan data to a filter-graph string, exactly like command_builder itself.
Subtitle rendering remains explicitly out of scope and untouched.

Audio mixing (ARCHITECTURE.md SS21 item 9, SS23 "Audio mixing") is
build_audio_filter_graph below, added alongside the pre-existing visual
graph builder rather than as a new module (this module's whole job is
"compile typed plan data into filter_complex fragments" - audio is more of
that, not a different responsibility): given a MusicPlan and the ffmpeg
input indices for the narration and (already-resolved-to-exist, by
music_library.resolve_music_asset + preflight.verify_music_asset_exists)
music track, it compiles a narration+music `amix` graph - music scaled to a
background level, muted or ducked per-cue via `volume`+`enable=between(...)`,
faded in/out via `afade` at the plan's own first/last non-silent cue
boundaries. Also pure - same no-I/O guarantee as everything else here.
command_builder only calls it once a music asset has actually resolved;
when none has, it keeps today's raw narration passthrough untouched, so this
function's absence from a render is itself the graceful-degrade path, not a
special case inside it.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from execution_engine.errors import RenderInputError
from execution_engine.ffmpeg_format import format_seconds
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderOptions

# Crossfade duration at a scene boundary, and fade duration at the very
# start/end of the whole edit - both capped (see the calls below) to half of
# the shorter clip involved, so a very short shot can never produce a
# negative offset or an overlap longer than the clip itself. The same capping
# approach Music Planning uses for its own fades.
CROSSFADE_SECONDS = 0.75
EDGE_FADE_SECONDS = 1.0

_RESOLUTION_RE = re.compile(r"^(\d+)x(\d+)$")


@dataclass(frozen=True)
class VisualFilterGraph:
    """The compiled graph plus the label of its final video output stream -
    command_builder maps this label directly (`-map "[label]"`); it never
    parses or re-derives it from the filter_complex string."""

    filter_complex: str
    video_output_label: str


def parse_resolution(resolution: str) -> Tuple[int, int]:
    """Public (not just this module's own concern): command_builder also
    needs the render's target width/height to synthesize a black-frame lavfi
    source for a shot Asset Validation tolerated as missing, so this parse is
    shared rather than duplicated."""
    match = _RESOLUTION_RE.match(resolution.strip())
    if not match:
        raise RenderInputError(f"Invalid resolution '{resolution}' - expected WIDTHxHEIGHT, e.g. '1920x1080'")
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        raise RenderInputError(f"Invalid resolution '{resolution}' - width and height must be positive")
    return width, height


def segment_duration(segment: EditingSegment) -> float:
    """Public: segmented_renderer.py needs the same per-segment/per-chain
    duration arithmetic this module already established, to replicate the
    accumulated-offset math outside a single filter_complex."""
    duration = segment.end_time - segment.start_time
    if duration <= 0:
        raise RenderInputError(
            f"Editing segment scene {segment.scene_id} shot {segment.shot_id} has a "
            f"non-positive duration ({segment.start_time} -> {segment.end_time})"
        )
    return duration


def validate_boundary_transitions(segments: List[EditingSegment]) -> None:
    first, last = segments[0], segments[-1]
    if first.transition_in not in ("fade_from_black", "cut"):
        raise RenderInputError(
            f"Unsupported opening transition '{first.transition_in}' on shot {first.shot_id} - "
            f"expected 'fade_from_black' or 'cut'"
        )
    if last.transition_out not in ("fade_to_black", "cut"):
        raise RenderInputError(
            f"Unsupported closing transition '{last.transition_out}' on shot {last.shot_id} - "
            f"expected 'fade_to_black' or 'cut'"
        )


def join_type(prev: EditingSegment, nxt: EditingSegment) -> str:
    """The transition between two adjacent shots, read from the plan and
    cross-checked for consistency - prev.transition_out and nxt.transition_in
    describe the same boundary and must agree, or the plan is malformed."""
    if prev.transition_out != nxt.transition_in:
        raise RenderInputError(
            f"Transition mismatch between shot {prev.shot_id} and shot {nxt.shot_id}: "
            f"transition_out='{prev.transition_out}' vs transition_in='{nxt.transition_in}'"
        )
    if prev.transition_out not in ("cut", "crossfade"):
        raise RenderInputError(
            f"Unsupported inter-shot transition '{prev.transition_out}' between shot "
            f"{prev.shot_id} and shot {nxt.shot_id} - only 'cut' and 'crossfade' are supported "
            f"between adjacent shots"
        )
    return prev.transition_out


def group_into_chains(segments: List[EditingSegment]) -> List[List[int]]:
    """Splits segments into runs joined by 'cut' - each run becomes one concat
    chain; a 'crossfade' join starts a new chain. For today's Editing Planner
    this always lines up with scene boundaries (cuts within a scene,
    crossfades between scenes), but the grouping is derived from the actual
    transition data, not from scene_id, so it stays correct if that ever
    changes.

    Public: segmented_renderer.py (execution_engine's high-memory-project
    fallback, see its module docstring) reuses this exact grouping to decide
    where one small ffmpeg process's inputs end and the next begins - a
    chain is always rendered by a single process since 'cut' needs no
    cross-process blending, while a 'crossfade' boundary is exactly where
    segmented_renderer inserts a separate, disk-based merge step."""
    chains: List[List[int]] = [[0]]
    for i in range(1, len(segments)):
        if join_type(segments[i - 1], segments[i]) == "cut":
            chains[-1].append(i)
        else:
            chains.append([i])
    return chains


def normalize_expr(width: int, height: int, fps: int) -> str:
    """Letterbox-scales to the target frame, pads to fill it, forces square
    pixels, and conforms frame rate - so image and video inputs of any source
    size/rate/SAR join cleanly in concat/xfade, which require matching
    formats across all their inputs."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )


def build_segment_chain(
    index: int, segment: EditingSegment, *, is_first: bool, is_last: bool, width: int, height: int, fps: int
) -> Tuple[List[str], str]:
    """Compiles one segment's own filter chain: trim (video only) + normalize,
    then an opening fade-from-black if this is the true first shot of the
    whole edit, then a closing fade-to-black if this is the true last shot -
    both independently gated on this segment's own transition_in/
    transition_out, so a single-segment edit can carry both.

    Public: segmented_renderer.py calls this per segment too, with `index`
    re-based to each chain's own local (0-based, per-process) input
    position rather than the segment's position in the whole edit - the
    label names this produces (n{index}/fi{index}/fo{index}) only need to
    be unique within the one filter_complex string they end up in, and a
    segmented chain's filter_complex is scoped to that chain's own ffmpeg
    process, never mixed with another chain's labels."""
    duration = segment_duration(segment)
    filters: List[str] = []
    current = f"n{index}"

    trim_expr = ""
    if segment.asset_type == "video":
        # Images (and "black" placeholder segments, via their lavfi `:d=`
        # parameter) are already exactly `duration` long via command_builder;
        # a video source is conformed to the plan's duration here, since
        # concat/xfade require every input's length to match what the plan
        # says, not what the source file happens to hold.
        trim_expr = f"trim=duration={format_seconds(duration)},setpts=PTS-STARTPTS,"
    filters.append(f"[{index}:v]{trim_expr}{normalize_expr(width, height, fps)}[{current}]")

    if is_first and segment.transition_in == "fade_from_black":
        fade_duration = min(EDGE_FADE_SECONDS, duration / 2)
        next_label = f"fi{index}"
        filters.append(f"[{current}]fade=t=in:st=0:d={format_seconds(fade_duration)}[{next_label}]")
        current = next_label

    if is_last and segment.transition_out == "fade_to_black":
        fade_duration = min(EDGE_FADE_SECONDS, duration / 2)
        fade_start = max(duration - fade_duration, 0)
        next_label = f"fo{index}"
        filters.append(
            f"[{current}]fade=t=out:st={format_seconds(fade_start)}:d={format_seconds(fade_duration)}[{next_label}]"
        )
        current = next_label

    return filters, current


def build_visual_filter_graph(editing_plan: EditingPlan, options: RenderOptions) -> VisualFilterGraph:
    """Compiles editing_plan.segments (in their existing order - Timeline
    Planning already sequenced them) into one filter_complex graph. Assumes
    command_builder's input ordering: input index i corresponds to
    editing_plan.segments[i], one -i per segment, in order, ahead of the
    narration audio input."""
    segments = editing_plan.segments
    if not segments:
        raise RenderInputError("Editing plan has no segments - cannot build a filter graph")

    width, height = parse_resolution(options.resolution)
    if options.fps <= 0:
        raise RenderInputError(f"Invalid fps '{options.fps}' - must be positive")

    validate_boundary_transitions(segments)
    chains = group_into_chains(segments)

    all_filters: List[str] = []
    segment_labels: Dict[int, str] = {}
    last_index = len(segments) - 1
    for i, segment in enumerate(segments):
        seg_filters, label = build_segment_chain(
            i, segment, is_first=(i == 0), is_last=(i == last_index), width=width, height=height, fps=options.fps,
        )
        all_filters.extend(seg_filters)
        segment_labels[i] = label

    chain_labels: List[str] = []
    chain_durations: List[float] = []
    for chain_index, chain in enumerate(chains):
        if len(chain) == 1:
            chain_labels.append(segment_labels[chain[0]])
        else:
            concat_inputs = "".join(f"[{segment_labels[idx]}]" for idx in chain)
            label = f"chain{chain_index}"
            # concat's output does not inherit its inputs' timebase (ffmpeg
            # resets it) even though every input was already normalized to
            # 1/fps via normalize_expr - re-asserting fps here keeps this
            # chain's output on the same timebase as every other node, which
            # xfade requires exact agreement on when this chain sits next to
            # one that never passed through concat.
            all_filters.append(f"{concat_inputs}concat=n={len(chain)}:v=1:a=0,fps={options.fps}[{label}]")
            chain_labels.append(label)
        chain_durations.append(sum(segment_duration(segments[idx]) for idx in chain))

    final_label = chain_labels[0]
    accumulated_duration = chain_durations[0]
    for i in range(1, len(chain_labels)):
        next_label = chain_labels[i]
        next_duration = chain_durations[i]
        xfade_duration = min(CROSSFADE_SECONDS, accumulated_duration / 2, next_duration / 2)
        offset = max(accumulated_duration - xfade_duration, 0)
        out_label = f"xf{i}"
        all_filters.append(
            f"[{final_label}][{next_label}]xfade=transition=fade:"
            f"duration={format_seconds(xfade_duration)}:offset={format_seconds(offset)}[{out_label}]"
        )
        final_label = out_label
        accumulated_duration = accumulated_duration + next_duration - xfade_duration

    return VisualFilterGraph(filter_complex=";".join(all_filters), video_output_label=final_label)


# ---- audio mixing (Milestone A - see module docstring) ----

# Resting/default level of the music bed relative to the (unfiltered,
# always-full-level) narration track - keeps music audibly present without
# ever competing with narration for "primary track" even in a gap between
# duck windows.
MUSIC_BASE_LEVEL = 0.6

# Multiplied on top of MUSIC_BASE_LEVEL during a duck window (a subtitle
# cue's speaking span) - not an absolute target level, so it composes
# correctly regardless of what MUSIC_BASE_LEVEL is tuned to.
MUSIC_DUCK_FACTOR = 0.3


@dataclass(frozen=True)
class AudioFilterGraph:
    """The compiled narration+music audio graph plus the label of its final
    mixed output stream - command_builder maps this label directly
    (`-map "[label]"`), the same convention VisualFilterGraph.video_output_label
    already establishes for the video side."""

    filter_complex: str
    audio_output_label: str


def _music_gain_windows(music_plan: MusicPlan) -> List[Tuple[float, float, float]]:
    """One (start, end, gain_factor) window per cue that needs the music
    bed pulled away from its MUSIC_BASE_LEVEL default: a silent cue's whole
    span mutes the bed entirely (gain 0.0 - Music Planning already decided
    this scene carries no music), and a non-silent cue's own duck_windows
    (one per subtitle cue in that scene) pull it down under narration
    (MUSIC_DUCK_FACTOR) without silencing it. Windows never overlap - cues
    partition the timeline by scene, and duck_windows lie inside their own
    cue's span - so the filters build_audio_filter_graph chains from this
    list compose correctly regardless of order; sorted by start_time purely
    for deterministic, readable output."""
    windows: List[Tuple[float, float, float]] = []
    for cue in music_plan.cues:
        if cue.is_silent:
            windows.append((cue.start_time, cue.end_time, 0.0))
        else:
            windows.extend((w.start_time, w.end_time, MUSIC_DUCK_FACTOR) for w in cue.duck_windows)
    return sorted(windows, key=lambda w: w[0])


def build_audio_filter_graph(
    music_plan: MusicPlan, *, narration_input_index: int, music_input_index: int
) -> AudioFilterGraph:
    """Pure: compiles the narration+music `amix` graph. Only ever called by
    command_builder once a music asset has actually resolved and been
    confirmed to exist (music_library.resolve_music_asset +
    verify_music_asset_exists, via preflight.py) - a render with no
    resolved music never calls this at all and keeps the original raw
    narration passthrough, which is the graceful-degrade path, not
    something this function itself needs to handle.

    Narration (`narration_input_index:a`) is mapped into the mix
    unfiltered, and `amix`'s own `normalize=0` keeps it that way - amix's
    default `normalize=1` would otherwise auto-divide EVERY input's gain by
    the input count, quietening narration along with music, which would
    violate "narration stays the primary/loud track". The music bed
    (`music_input_index:a`) is scaled to MUSIC_BASE_LEVEL, then muted or
    ducked per _music_gain_windows, then faded in/out via `afade` using
    MusicPlan's own first and last non-silent cue's already-computed
    fade_in_seconds/fade_out_seconds - and ONLY those two, not every
    interior cue's fade. Milestone A mixes one continuous track for the
    whole video (see command_builder's single music `-i` input), so an
    interior cue's fade_in/fade_out (planned for a future per-scene
    track-switching milestone, where they'd smooth an actual file change at
    that scene boundary) has nothing to smooth here - applying it anyway
    would just dip the one continuous file's volume at every scene
    boundary for no reason a viewer could attribute to anything happening
    on screen or in the narration."""
    current = f"{music_input_index}:a"
    filters: List[str] = [f"[{current}]volume={MUSIC_BASE_LEVEL:g}[mbase]"]
    current = "mbase"

    for i, (start, end, gain) in enumerate(_music_gain_windows(music_plan)):
        label = f"mgain{i}"
        filters.append(
            f"[{current}]volume={gain:g}:enable='between(t,{format_seconds(start)},{format_seconds(end)})'[{label}]"
        )
        current = label

    non_silent = [cue for cue in music_plan.cues if not cue.is_silent]
    if non_silent:
        first_cue = non_silent[0]
        if first_cue.fade_in_seconds > 0:
            filters.append(
                f"[{current}]afade=t=in:st={format_seconds(first_cue.start_time)}:"
                f"d={format_seconds(first_cue.fade_in_seconds)}[mfadein]"
            )
            current = "mfadein"

        last_cue = non_silent[-1]
        if last_cue.fade_out_seconds > 0:
            fade_start = max(last_cue.end_time - last_cue.fade_out_seconds, 0.0)
            filters.append(
                f"[{current}]afade=t=out:st={format_seconds(fade_start)}:"
                f"d={format_seconds(last_cue.fade_out_seconds)}[mfadeout]"
            )
            current = "mfadeout"

    filters.append(
        f"[{narration_input_index}:a][{current}]amix=inputs=2:duration=first:"
        f"dropout_transition=0:normalize=0[aout]"
    )

    return AudioFilterGraph(filter_complex=";".join(filters), audio_output_label="aout")

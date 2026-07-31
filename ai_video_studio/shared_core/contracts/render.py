from datetime import UTC, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline


class RenderOptions(BaseModel):
    """Execution-technical configuration only - no content decisions live here
    (those were all made during planning). resolution is applied during the
    filter-graph stage, a later Execution Engine milestone; in 8.1 it is
    carried but not yet emitted into output_args.

    preset default is "ultrafast", not libx264's own "medium" default:
    Release-Prep milestone found "medium"'s larger reference-frame/lookahead
    buffers push a multi-scene 1080p render (several 1080p frames held
    concurrently for concat/xfade compositing) past this deployment's 1GB
    container ceiling, killing ffmpeg with SIGKILL. Reproduced under a real
    1GB/2vCPU container that also carries a ~150-300MB concurrent memory
    footprint (matching the FastAPI/uvicorn process ffmpeg actually shares
    the container with in production, not an idle container to itself):
    under that realistic headroom, "fast", "superfast", and even "veryfast"
    all still failed. "ultrafast" was believed to hold consistently with an
    extra safety margin, but production RSS telemetry gathered afterward
    disproved that: the ffmpeg child's own peak RSS for this render sits at
    ~860MB (84%+ of the 1GB ceiling) regardless of preset, and the render was
    still observed to SIGKILL intermittently - see threads below, the next
    lever this milestone actually found and tuned."""

    resolution: str = "1920x1080"
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 20
    preset: str = "ultrafast"
    # Was libx264's own auto-detect (0 = one encode thread per detected CPU).
    # Release-Prep milestone found that even "ultrafast" still SIGKILLs this
    # deployment's 1080p multi-scene render intermittently: production RSS
    # telemetry (ffmpeg_executor's peak-RSS diagnostic) showed the ffmpeg
    # child alone consistently using ~860MB of the container's 1GB ceiling
    # regardless of preset - preset only trims encoder lookahead/reference
    # buffers, not the per-thread reconstruction buffers frame-parallel
    # threading allocates, so it was never actually addressing this. preset
    # is already at its floor (ultrafast); threads is the next real memory
    # lever and was never tuned. 1 disables frame-parallel encoding, trading
    # some encode speed (still well inside timeout_seconds) for a smaller,
    # single-threaded encoder memory footprint - the goal is real headroom
    # for the FastAPI/uvicorn process ffmpeg shares the container with, not
    # just a number that happened to survive one test run.
    threads: int = 1
    pix_fmt: str = "yuv420p"
    subtitle_mode: str = "soft"  # "soft" | "burn" - consumed by a later milestone
    dry_run: bool = False
    # Was None (no timeout) - Release-Prep milestone found that under memory
    # pressure this deployment's ffmpeg render can stall indefinitely at the
    # container's memory ceiling (near-zero CPU, memory pinned at the limit)
    # rather than being cleanly killed, hanging the run forever and starving
    # the whole service of memory with no automatic recovery. 120s is well
    # above every observed successful render's real duration (under 30s, even
    # under memory pressure) but still bounds the worst case - ffmpeg_executor
    # already handles TimeoutExpired as a normal, reportable RenderResult
    # failure (error_type="timeout"); this default just lets that path fire
    # instead of hanging.
    timeout_seconds: Optional[int] = 120


class FFmpegInfo(BaseModel):
    """Result of detecting the ffmpeg binary. Deliberately never raises on its
    own - detection reports availability as data, and the controller decides
    whether an unavailable binary is fatal (it is, via ExecutionEnvironmentError)."""

    available: bool
    path: Optional[str] = None
    version: Optional[str] = None
    raw_version_line: Optional[str] = None


class FFmpegInput(BaseModel):
    """One `-i` input in the eventual ffmpeg command, plus the per-input args
    that precede it (e.g. an image becomes a finite clip via `-loop 1 -t <dur>`).
    scene_id/shot_id are carried for traceability back to the editing plan;
    they are None for the narration audio input. Frozen (Milestone 8.3): once
    command_builder hands a command to the executor, nothing downstream may
    mutate it - the executor is a pure consumer, not a co-author, of the
    command it runs."""

    model_config = ConfigDict(frozen=True)

    path: str
    kind: str  # "image" | "video" | "audio" | "black"
    scene_id: Optional[int] = None
    shot_id: Optional[int] = None
    duration_seconds: Optional[float] = None
    pre_input_args: List[str] = Field(default_factory=list)


class FFmpegCommandSpec(BaseModel):
    """A typed, inspectable representation of an ffmpeg invocation - built and
    validated without ever executing (ARCHITECTURE.md: command_builder is pure,
    the executor is a separate boundary). filter_complex holds the visual
    timeline's compiled graph (cut/fade/xfade plus resolution/fps
    normalization, from filter_graph_builder) as of Milestone 8.2; audio
    mixing and subtitle burn-in remain deferred to later milestones.
    output_args carries the render configuration (codec/crf/preset) plus the
    -map arguments the compiled graph requires, so this object fully expresses
    'what would be run'.

    Frozen (Milestone 8.3): this is the exact object ffmpeg_executor.execute()
    consumes, and it consumes it as pure execution input - the executor never
    adjusts a codec, a filter, or an arg; freezing makes that guarantee
    structural rather than just conventional."""

    model_config = ConfigDict(frozen=True)

    global_args: List[str] = Field(default_factory=list)
    inputs: List[FFmpegInput] = Field(default_factory=list)
    filter_complex: Optional[str] = None
    output_args: List[str] = Field(default_factory=list)
    output_path: str = ""

    def to_argv(self, ffmpeg_path: str = "ffmpeg") -> List[str]:
        """Assembles the full argument vector in canonical order: globals, then
        each input (with its pre-input args), then the filter graph if present,
        then the output args and path."""
        argv: List[str] = [ffmpeg_path, *self.global_args]
        for inp in self.inputs:
            argv.extend([*inp.pre_input_args, "-i", inp.path])
        if self.filter_complex:
            argv.extend(["-filter_complex", self.filter_complex])
        argv.extend([*self.output_args, self.output_path])
        return argv


class RenderRequest(BaseModel):
    """The typed bundle the Execution Engine consumes - every Producer Package
    artifact the render needs, reconstructed by Project Manager, plus the
    render output directory it provided and the caller's options. The engine
    never opens these files itself; it operates on this typed request."""

    editing_plan: EditingPlan
    asset_manifest: ValidatedAssetManifest
    timeline: Timeline
    subtitle_plan: SubtitlePlan
    music_plan: MusicPlan
    output_dir: str
    options: RenderOptions = Field(default_factory=RenderOptions)


class RenderResult(BaseModel):
    """The Execution Engine's structured EXECUTION-PROCESS outcome (Milestone
    8.3) - what ffmpeg_executor.execute() always returns instead of raising,
    and what a --dry-run also produces (with dry_run=True and nothing else
    populated) so the controller's return shape is uniform whether or not it
    actually ran ffmpeg. success=True here means only that the subprocess
    exited 0 and wrote a non-empty file to output_path - it is process
    diagnostics, NOT content verification (duration/stream correctness).
    Persisted to renders/render_report.json (project_manager/render_writer.py)
    for every attempted (non-dry-run) render, success or failure - kept
    deliberately separate from render_validation.json's output-quality
    verdict (RenderValidationReport, Milestone 8.4). project.status is never
    advanced on a RenderResult alone; see RenderValidationReport."""

    success: bool
    dry_run: bool = False
    output_path: Optional[str] = None
    exit_code: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # "ffmpeg_failed" | "timeout" | "spawn_error" | None
    stderr_tail: Optional[str] = None


class ProbedMedia(BaseModel):
    """Raw ffprobe facts about a rendered file - no business meaning attached
    yet, the same convention ScannedMediaFile establishes for Asset
    Validation: a boundary module (ffprobe_client) gathers these facts, and a
    pure module (postflight) interprets them against what the render was
    supposed to produce."""

    duration_seconds: Optional[float] = None
    has_video_stream: bool = False
    video_width: Optional[int] = None
    video_height: Optional[int] = None
    video_fps: Optional[float] = None
    video_codec: Optional[str] = None
    has_audio_stream: bool = False
    audio_codec: Optional[str] = None


class RenderValidationCheck(BaseModel):
    """One concrete, human-readable postflight comparison - the same
    "reportable, not exceptional" convention ValidationIssue established for
    Asset Validation: each check names what was expected and what was
    actually found, so a failed render's validation report is directly
    actionable rather than a single opaque bool."""

    name: str  # "video_stream" | "audio_stream" | "resolution" | "fps" | "duration" | "probe"
    passed: bool
    expected: str
    actual: str


class RenderValidationReport(BaseModel):
    """Postflight OUTPUT-QUALITY verdict (Milestone 8.4) - deliberately
    separate from RenderResult's process diagnostics, persisted to its own
    renders/render_validation.json. is_valid=True is the ONLY thing that
    permits ExecutionEngineController to advance project.status to
    VIDEO_RENDERED: a successful ffmpeg exit (RenderResult.success) is
    necessary but not sufficient - the rendered file must also actually match
    the render's own expected profile (duration, resolution, fps, both
    streams present). Written only when a render produced a file to probe
    (RenderResult.success=True); there is nothing to validate otherwise."""

    is_valid: bool
    checks: List[RenderValidationCheck] = Field(default_factory=list)
    probed: Optional[ProbedMedia] = None
    output_path: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

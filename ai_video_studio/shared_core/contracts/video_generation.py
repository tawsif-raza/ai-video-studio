"""
Contracts for the Video Generation Engine (ARCHITECTURE.md SS25) - the fifth
top-level component, a peer to render.py (Execution Engine) and publish.py
(Publishing Engine), and following their exact shape: an Options input, a
Request bundle, a process-outcome Result, an async Status poll type, and a
separate verification Report (SS25.4's "process success is necessary but not
sufficient" discipline, the same one that gates VIDEO_RENDERED).

Credentials are never a field on any of these - resolved live, inside each
provider adapter only, from config.py/environment, never logged, serialized,
or written to any package file or report (the same rule SS24.3 already
established for the Publishing Engine).

PromptSet and ShotPrompt (prompt_set.py) are not modified - video_motion_prompt
already exists there and is consumed read-only by this module's Request type.

Milestone V2 amendment (Stub Provider Foundation): VideoGenerationOptions
gains one field beyond SS25.4's original table, `fps: int = 30`, mirroring
RenderOptions.fps. SS25.4 was written before any provider (even a local one)
existed to need a concrete frame rate; the first real implementation (the
zero-cost local StubProvider, SS25.16) needs one to synthesize a clip, so this
is recorded here as the amendment ARCHITECTURE.md SS2 requires rather than a
silent addition. VideoGenerationManifest also carries `results`/
`validation_reports` beyond SS25.4's table, matching what SS25.10's own output
specification already says video_manifest.json holds (the process-vs-
verification diagnostics pair, mirroring render_report.json/
render_validation.json) - SS25.4's table simply omitted them, it did not
contradict SS25.10.
"""

import uuid
from datetime import UTC, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from shared_core.contracts.prompt_set import ShotPrompt
from shared_core.contracts.render import ProbedMedia


class VideoGenerationOptions(BaseModel):
    """Execution-technical configuration only - no content decisions live
    here (those were already made by Prompt Intelligence and live on
    ShotPrompt.video_motion_prompt). Mirrors RenderOptions'/PublishOptions'
    role for their own engines (SS25.4).

    provider defaults to "google_veo" - the milestone's named first target -
    deliberately NOT the locally-registered stub provider: a caller must
    explicitly opt into the zero-cost stub (provider="stub") rather than a
    bare default ever silently reaching for it, the same "explicit, not
    implicit" discipline PublishOptions.visibility_override already applies
    to publishing visibility. Since no google_veo adapter is registered yet
    (SS25.5/SS25.15), resolving the bare default fails closed with
    VideoGenerationInputError until a later milestone registers one."""

    provider: str = "google_veo"
    aspect_ratio: str = "9:16"
    resolution: Optional[str] = None  # None defers to the provider's own default
    fps: int = 30  # V2 amendment - see module docstring
    seed_image_path: Optional[str] = None
    dry_run: bool = False
    timeout_seconds: Optional[int] = None
    poll_interval_seconds: int = 10
    max_poll_attempts: int = 60


class ProviderInfo(BaseModel):
    """Result of a provider adapter's authenticate() call - mirrors
    FFmpegInfo's/AuthenticationResult's "reports availability as data, never
    raises on its own" convention. The controller decides whether an
    unavailable/unauthenticated provider is fatal."""

    provider: str
    available: bool
    account_label: Optional[str] = None  # never a token/credential value
    detail: Optional[str] = None


class VideoGenerationRequest(BaseModel):
    """The typed bundle a VideoGenerationProvider.generate() call consumes -
    mirrors RenderRequest's/PublishRequest's role. shot_prompt is the existing
    ShotPrompt contract, reused read-only for its video_motion_prompt.
    scene_id/shot_id are carried alongside shot_prompt (which already has its
    own) for the same traceability reason FFmpegInput carries them - cheap,
    direct access without dereferencing shot_prompt, and a place for
    request_builder.validate_generation_request to cross-check consistency."""

    shot_prompt: ShotPrompt
    scene_id: int
    shot_id: int
    output_dir: str
    options: VideoGenerationOptions = Field(default_factory=VideoGenerationOptions)


class VideoAsset(BaseModel):
    """Public output - what Asset Validation discovers next in media/video/,
    mirroring ImageAsset's role for image generation."""

    asset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scene_id: int
    shot_id: int
    file_path: str
    prompt_used: str
    provider: str
    external_job_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VideoGenerationStatus(BaseModel):
    """One async-poll snapshot of an in-flight generation job - same role
    PublishingPlatform.check_status()'s return plays for an upload. A
    synchronous provider (the local stub) has no real job to poll and simply
    reports an immediate terminal status, for shape symmetry with a real
    async provider rather than because polling means anything for it."""

    status: str  # "pending" | "generating" | "succeeded" | "failed"
    external_job_id: str
    progress_pct: Optional[float] = None
    detail: Optional[str] = None


class VideoGenerationResult(BaseModel):
    """The Video Generation Engine's structured PROCESS outcome - mirrors
    RenderResult/PublishResult. success=True means only that the provider
    accepted and completed the job - process diagnostics, NOT verified media
    quality (see VideoGenerationValidationReport). Deliberately carries no
    file_path: the output location is a deterministic function of
    (output_dir, scene_id, shot_id) - the same scene_<id>_shot_<id>.mp4
    naming convention Asset Validation already expects from a human
    (SS25.10) - so the controller/postflight derive it rather than trust an
    arbitrary path echoed back by a provider."""

    success: bool
    dry_run: bool = False
    provider: str = ""
    scene_id: int
    shot_id: int
    external_job_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    retry_count: int = 0
    error: Optional[str] = None
    error_type: Optional[str] = None
    # "generation_failed" | "auth_failed" | "timeout" | "quota_exceeded" | "content_filtered" | None


class VideoGenerationValidationCheck(BaseModel):
    """One concrete, human-readable postflight comparison - mirrors
    RenderValidationCheck's/PublishValidationCheck's role."""

    name: str  # "video_stream" | "duration" | "probe"
    passed: bool
    expected: str
    actual: str


class VideoGenerationValidationReport(BaseModel):
    """Postflight OUTPUT-QUALITY verdict - mirrors RenderValidationReport's
    role exactly, including reusing shared_core.contracts.render.ProbedMedia
    directly (a generated clip and a rendered clip are probed the same way,
    SS25.4). is_valid=True is the only thing that gates a shot's clip being
    trusted, the same role RenderValidationReport.is_valid plays for
    VIDEO_RENDERED."""

    is_valid: bool
    checks: List[VideoGenerationValidationCheck] = Field(default_factory=list)
    probed: Optional[ProbedMedia] = None
    output_path: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ShotMediaSelection(BaseModel):
    """Per-shot mode selection (SS25.3) - new, additive, and deliberately not
    a field on PromptSet/ShotPrompt or any other Director Studio output.
    Absence of a selection for a given shot defaults to "image" - today's
    only behavior - so a project that never touches this engine behaves
    identically to today, byte for byte."""

    scene_id: int
    shot_id: int
    mode: str = "image"  # "image" | "video"


class VideoGenerationManifest(BaseModel):
    """Project-level record - Production Package's video_manifest.json
    (SS25.10). Written incrementally as shots complete; results/
    validation_reports are the same process-vs-verification split as
    render_report.json/render_validation.json, kept together here (one file)
    rather than two, since SS25.10 describes video_manifest.json as already
    holding both."""

    manifest_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_prompt_set_id: str = ""
    selections: List[ShotMediaSelection] = Field(default_factory=list)
    assets: List[VideoAsset] = Field(default_factory=list)
    results: List[VideoGenerationResult] = Field(default_factory=list)
    validation_reports: List[VideoGenerationValidationReport] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from shared_core.contracts.render import RenderOptions
from web_api.run_registry import RunStatus


class HealthResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    api_version: str
    service: str = "ai-video-studio-api"


class CreateProjectRequest(BaseModel):
    """Mirrors app.py's flags (WEB_DASHBOARD_ARCHITECTURE.md SS7.3).
    generate_images/skip_images are deliberately omitted - image generation
    is an explicit, opt-in manual tool even on the CLI (ARCHITECTURE.md
    SS2/SS15 Phase 6), out of scope for triggering a project from the
    dashboard in this milestone."""

    idea: str
    duration_seconds: int = 150
    tone: Optional[str] = None
    audience: Optional[str] = None
    art_style: Optional[str] = None
    skip_research: bool = False


class RunAccepted(BaseModel):
    project_id: str
    run_id: str
    status: RunStatus


class MediaUploadResponse(BaseModel):
    filename: str
    path: str
    size_bytes: int


class MediaCategory(str, Enum):
    """Mirrors the three subdirectory names save_uploaded_media/scan_media/
    delete_uploaded_media already use (project_manager/manager.py) -
    declared here, not re-derived from ImportedMediaManifest's "images"/
    "videos"/"audio" field names, since the filesystem's own directory is
    "video" (singular) while the manifest field is "videos" (plural) - an
    existing asymmetry (WEB_DASHBOARD_ARCHITECTURE.md); this enum matches
    the filesystem/ProjectManager side, which is what the delete path
    actually operates on."""

    IMAGES = "images"
    VIDEO = "video"
    AUDIO = "audio"


class MediaDeleteItem(BaseModel):
    category: MediaCategory
    filename: str


class BulkMediaDeleteRequest(BaseModel):
    """Milestone W10 SS3: one call deletes many files. Deliberately not
    wrapped in a single filesystem transaction (plain files have no such
    primitive) - each item is deleted independently and reported
    individually in BulkMediaDeleteResponse, "atomic where practical"
    meaning each single file removal (unlink) is itself atomic, not that
    the whole batch either fully succeeds or fully no-ops."""

    items: List[MediaDeleteItem]


class MediaDeleteResult(BaseModel):
    category: MediaCategory
    filename: str
    success: bool
    error: Optional[str] = None


class BulkMediaDeleteResponse(BaseModel):
    results: List[MediaDeleteResult]


class RenderRunRequest(BaseModel):
    """Mirrors render_app.py's flags (RenderOptions' fields + dry_run),
    same convention as CreateProjectRequest mirroring app.py's. Every
    field defaults to exactly what RenderOptions/render_app.py's argparse
    already default to, so a bodyless POST behaves the same as running
    render_app.py with no flags."""

    resolution: str = "1920x1080"
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 20
    preset: str = "ultrafast"
    threads: int = 1
    pix_fmt: str = "yuv420p"
    subtitle_mode: str = "soft"
    dry_run: bool = False
    timeout_seconds: Optional[int] = 120

    def to_render_options(self) -> RenderOptions:
        return RenderOptions(**self.model_dump())


class RenderStatusResponse(BaseModel):
    """Presentation-only derivation over the existing, unmodified Run model
    (run_registry.py) - no new state is stored anywhere for this; status,
    current_stage, and progress are all computed from Run.status at
    request time. Deliberately coarse per this milestone's scope: the
    controller reports nothing between "started" and "finished," so
    current_stage/progress can only reflect that same coarse granularity,
    not fabricate detail the Execution Engine doesn't emit."""

    run_id: str
    status: RunStatus
    current_stage: str
    progress: int
    started_at: datetime
    updated_at: datetime
    error: Optional[str] = None


class PublishRunRequest(BaseModel):
    """Mirrors publish_app.py's flags. dry_run is threaded straight through
    to ReadyToPublishResult.dry_run, exactly as the CLI does - it has no
    upload to skip yet, since neither the CLI nor this endpoint triggers
    one (PublishingEngineController.run() never uploads;
    WEB_DASHBOARD_ARCHITECTURE.md SS12 keeps real upload-triggering out of
    scope for the dashboard)."""

    platform: str = "youtube"
    dry_run: bool = False


class PublishStatusResponse(BaseModel):
    """Same presentation-only derivation convention as RenderStatusResponse.
    project_state is the one addition beyond the render status shape - the
    project's actual current ProjectState (project_manager/project.py),
    read fresh at request time, not stored on Run. A successful readiness-
    only publish run never changes it (save_publish_report never advances
    project.status, by design - there is no PUBLISHED state to advance to
    yet); this field simply reports whatever it already is, honestly,
    rather than implying a transition this milestone's controller doesn't
    perform."""

    run_id: str
    status: RunStatus
    current_stage: str
    progress: int
    started_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    project_state: str

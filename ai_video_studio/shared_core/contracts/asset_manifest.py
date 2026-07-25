import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ScannedMediaFile(BaseModel):
    """Raw filesystem fact Project Manager discovers by scanning a project's
    media/ directory (ARCHITECTURE.md SS5/SS14: studios never touch the
    filesystem themselves) - no business meaning attached yet. Asset Validation
    interprets these against what the Production Package expects."""

    filename: str
    path: str
    size_bytes: int
    sha256: str


class ImportedMediaManifest(BaseModel):
    """Typed inventory Project Manager builds by scanning media/images,
    media/video, and media/audio. This is the typed argument Asset Validation
    receives instead of ever opening a directory itself."""

    images: List[ScannedMediaFile] = Field(default_factory=list)
    videos: List[ScannedMediaFile] = Field(default_factory=list)
    audio: List[ScannedMediaFile] = Field(default_factory=list)


class ValidatedAsset(BaseModel):
    """One shot's resolved media coverage - image_path and/or video_path are
    None when that shot has no usable asset yet."""

    scene_id: int
    shot_id: int
    image_path: Optional[str] = None
    video_path: Optional[str] = None


class ValidationIssue(BaseModel):
    """One concrete, human-readable problem found during validation - this is
    the report a human acts on to fix their media/ folder."""

    category: str  # "missing" | "duplicate" | "naming" | "narration"
    description: str


class ValidatedAssetManifest(BaseModel):
    """Public output contract (ARCHITECTURE.md SS6/SS12): Asset Validation's
    report today, and Timeline Planning's input in a future milestone."""

    manifest_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_prompt_set_id: str = ""
    assets: List[ValidatedAsset] = Field(default_factory=list)
    narration_audio_path: Optional[str] = None
    issues: List[ValidationIssue] = Field(default_factory=list)
    is_valid: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)

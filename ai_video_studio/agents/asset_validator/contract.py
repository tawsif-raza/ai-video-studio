from pydantic import BaseModel

from shared_core.contracts.asset_manifest import (
    ImportedMediaManifest,
    ScannedMediaFile,
    ValidatedAsset,
    ValidatedAssetManifest,
    ValidationIssue,
)
from shared_core.contracts.prompt_set import PromptSet

__all__ = [
    "ImportedMediaManifest",
    "PromptSet",
    "ScannedMediaFile",
    "ValidatedAsset",
    "ValidatedAssetManifest",
    "ValidationIssue",
    "AssetValidatorInput",
]


class AssetValidatorInput(BaseModel):
    """Typed input assembled by Project Manager: expected shot coverage (from
    Prompt Intelligence's PromptSet) plus the raw media inventory already
    scanned from the project's media/ directory. Asset Validation never touches
    a filesystem itself (ARCHITECTURE.md SS5/SS14)."""

    prompt_set: PromptSet
    imported_media: ImportedMediaManifest

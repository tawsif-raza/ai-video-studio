"""
Typed shape of the Production Package (ARCHITECTURE.md SS7, SS9): the single
canonical source of truth for every Package Schema type. Individual agents'
contract.py/schema.py files import from here rather than redefining these
types or importing them from another agent's module (SS14).
"""

from shared_core.contracts.asset_manifest import (
    ImportedMediaManifest,
    ScannedMediaFile,
    ValidatedAsset,
    ValidatedAssetManifest,
    ValidationIssue,
)
from shared_core.contracts.camera_plan import CameraPlan, CameraPlannerSchema, CameraScenePlan, CameraShot
from shared_core.contracts.character_sheet import CharacterPlannerSchema, CharacterSheet, CharacterVisualProfile
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.environment_sheet import EnvironmentPlannerSchema, EnvironmentProfile, EnvironmentSheet
from shared_core.contracts.music_plan import DuckWindow, MusicCue, MusicPlan, SceneMood
from shared_core.contracts.production_plan import CharacterBrief, ProductionPlan, SceneBrief, StoryPlanSchema
from shared_core.contracts.prompt_set import PromptSet, ShotPrompt, ShotPromptSchema
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata
from shared_core.contracts.render import (
    FFmpegCommandSpec,
    FFmpegInfo,
    FFmpegInput,
    ProbedMedia,
    RenderOptions,
    RenderRequest,
    RenderResult,
    RenderValidationCheck,
    RenderValidationReport,
)
from shared_core.contracts.research import ResearchBrief, ResearchSchema
from shared_core.contracts.shot_plan import ShotItem, ShotPlan, ShotPlannerSchema, ShotScenePlan
from shared_core.contracts.storyboard import ScenePlan, ScenePlannerSchema, ShotBrief, Storyboard
from shared_core.contracts.subtitle import SubtitleCue, SubtitlePlan
from shared_core.contracts.thumbnail_plan import TextSafeArea, ThumbnailPlan, ThumbnailVariant
from shared_core.contracts.timeline import ShotDuration, Timeline, TimelineClip, VoiceSegment
from shared_core.contracts.voice_script import NarrationLine, VoiceScript, VoiceScriptSchema

__all__ = [
    "ImportedMediaManifest",
    "ScannedMediaFile",
    "ValidatedAsset",
    "ValidatedAssetManifest",
    "ValidationIssue",
    "CameraPlan",
    "CameraPlannerSchema",
    "CameraScenePlan",
    "CameraShot",
    "CharacterBrief",
    "CharacterPlannerSchema",
    "CharacterSheet",
    "CharacterVisualProfile",
    "EditingPlan",
    "EditingSegment",
    "EnvironmentPlannerSchema",
    "EnvironmentProfile",
    "EnvironmentSheet",
    "DuckWindow",
    "MusicCue",
    "MusicPlan",
    "SceneMood",
    "NarrationLine",
    "ProductionPlan",
    "PromptSet",
    "PublishingMetadata",
    "PublishingPlan",
    "YouTubeMetadata",
    "FFmpegCommandSpec",
    "FFmpegInfo",
    "FFmpegInput",
    "ProbedMedia",
    "RenderOptions",
    "RenderRequest",
    "RenderResult",
    "RenderValidationCheck",
    "RenderValidationReport",
    "ResearchBrief",
    "ResearchSchema",
    "SceneBrief",
    "ScenePlan",
    "ScenePlannerSchema",
    "ShotBrief",
    "ShotItem",
    "ShotPlan",
    "ShotPlannerSchema",
    "ShotPrompt",
    "ShotPromptSchema",
    "ShotScenePlan",
    "StoryPlanSchema",
    "Storyboard",
    "SubtitleCue",
    "SubtitlePlan",
    "TextSafeArea",
    "ThumbnailPlan",
    "ThumbnailVariant",
    "ShotDuration",
    "Timeline",
    "TimelineClip",
    "VoiceSegment",
    "VoiceScript",
    "VoiceScriptSchema",
]

/**
 * Mirrors the exact JSON shapes GET /projects/{id}/production-package and
 * .../producer-package return (W7.5's ProjectManager.load_production_package
 * / load_producer_package - a verbatim read-back of whatever
 * package_writer.py / producer_package_writer.py already wrote, keyed by
 * literal filename). Some values are full contract dumps
 * (shared_core/contracts/*.py); others are hand-built projections
 * package_writer.py itself decided the shape of (scene_plan.json,
 * shot_plan.json, camera_plan.json, image_prompts.json, video_prompts.json)
 * - these types describe what's actually on the wire today, not a
 * re-derived schema.
 */

export interface PackageManifestFile {
  name: string;
  description: string;
  status: string;
}

export interface PackageManifest {
  package_id: string;
  generated_at?: string;
  files: PackageManifestFile[];
}

// ---- Production Package (production-package/*) ----

export interface ProductionPackageMetadata {
  package_id: string;
  source_plan_id: string;
  source_storyboard_id: string;
  generated_at: string;
  target_duration_seconds: number;
  tone: string | null;
  audience: string | null;
  art_style: string | null;
}

export interface ResearchBriefSkipped {
  status: "skipped";
  reason: string;
}
export interface ResearchBriefContent {
  key_facts: string[];
  considerations: string[];
  source_idea: string;
  brief_id: string;
  generated_at: string;
}
export type ResearchBriefFile = ResearchBriefSkipped | ResearchBriefContent;
export function isResearchSkipped(brief: ResearchBriefFile): brief is ResearchBriefSkipped {
  return "status" in brief && brief.status === "skipped";
}

export interface SceneEntry {
  scene_id: number;
  title: string;
  summary: string;
  setting: string;
  mood: string;
  characters_present: string[];
  estimated_duration_seconds: number;
}

export interface ShotEntry {
  shot_id: number;
  description: string;
  characters_in_shot: string[];
  duration_seconds: number;
}
export interface ShotPlanScene {
  scene_id: number;
  shots: ShotEntry[];
}

export interface CameraShotEntry {
  shot_id: number;
  camera_angle: string;
  camera_movement: string;
}
export interface CameraPlanScene {
  scene_id: number;
  shots: CameraShotEntry[];
}

export interface ImagePromptEntry {
  scene_id: number;
  shot_id: number;
  image_prompt: string;
}
export interface VideoPromptEntry {
  scene_id: number;
  shot_id: number;
  video_motion_prompt: string;
}

export interface ProductionPackage {
  "manifest.json": PackageManifest;
  "metadata.json": ProductionPackageMetadata;
  "research_brief.json": ResearchBriefFile;
  "story.md": string;
  "scene_plan.json": SceneEntry[];
  "shot_plan.json": ShotPlanScene[];
  "camera_plan.json": CameraPlanScene[];
  "image_prompts.json": ImagePromptEntry[];
  "video_prompts.json": VideoPromptEntry[];
  "voice_script.txt": string;
  [key: string]: unknown;
}

// ---- Producer Package (producer-package/*) ----

export interface TimelineClipEntry {
  scene_id: number;
  shot_id: number;
  asset_type: string;
  duration_seconds: number;
  start_time: number;
  end_time: number;
  // asset_path deliberately omitted from this type - the real field is a
  // raw server filesystem path (project_manager/manager.py's
  // ScannedMediaFile.path flows into it via Asset Validation), and this
  // app never renders it. See the Timeline tab and the W8 report's
  // technical-debt note.
}
export interface VoiceSegmentEntry {
  scene_id: number;
  start_time: number;
  end_time: number;
}
export interface TimelinePlan {
  timeline_id: string;
  source_asset_manifest_id: string;
  clips: TimelineClipEntry[];
  voice_segments: VoiceSegmentEntry[];
  total_duration_seconds: number;
  generated_at: string;
}

export interface PublishingMetadataCanonical {
  title: string;
  description: string;
  keywords: string[];
  hashtags: string[];
  category: string;
  language: string;
}
export interface YouTubeMetadata {
  title: string;
  description: string;
  tags: string[];
  category: string;
  default_language: string;
  playlist: string;
  visibility: string;
}
export interface PublishingPlan {
  publishing_plan_id: string;
  source_editing_plan_id: string;
  source_thumbnail_plan_id: string;
  canonical: PublishingMetadataCanonical;
  youtube: YouTubeMetadata;
  generated_at: string;
}

export interface ProducerPackage {
  "manifest.json": PackageManifest;
  "timeline_plan.json"?: TimelinePlan;
  "publishing_metadata.json"?: PublishingPlan;
  [key: string]: unknown;
}

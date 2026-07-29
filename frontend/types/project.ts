/**
 * Mirrors project_manager/project.py's ProjectState enum and Project model
 * exactly - field-for-field, including which fields are optional. This is
 * the only place that mapping lives; nothing else in the frontend should
 * redeclare it.
 */
export type ProjectState =
  | "CREATED"
  | "RESEARCHED"
  | "STORY_COMPLETE"
  | "SCENES_COMPLETE"
  | "SHOTS_COMPLETE"
  | "CAMERA_COMPLETE"
  | "CHARACTERS_COMPLETE"
  | "ENVIRONMENTS_COMPLETE"
  | "PROMPTS_COMPLETE"
  | "PACKAGE_READY"
  | "MEDIA_IMPORTED"
  | "EDIT_PLAN_READY"
  | "VIDEO_RENDERED";

/**
 * Pipeline order, for a simple production-progress stepper. RESEARCHED is
 * skippable (--skip-research), so a project can legitimately jump straight
 * from CREATED to STORY_COMPLETE - this list is a presentational
 * simplification, not a claim that every project passes through every
 * step in order.
 */
export const PROJECT_STATE_ORDER: ProjectState[] = [
  "CREATED",
  "RESEARCHED",
  "STORY_COMPLETE",
  "SCENES_COMPLETE",
  "SHOTS_COMPLETE",
  "CAMERA_COMPLETE",
  "CHARACTERS_COMPLETE",
  "ENVIRONMENTS_COMPLETE",
  "PROMPTS_COMPLETE",
  "PACKAGE_READY",
  "MEDIA_IMPORTED",
  "EDIT_PLAN_READY",
  "VIDEO_RENDERED",
];

export interface Project {
  project_id: string;
  status: ProjectState;
  created_at: string;
  source_research_brief_id: string | null;
  source_plan_id: string | null;
  source_storyboard_id: string | null;
  source_shot_plan_id: string | null;
  source_camera_plan_id: string | null;
  source_character_sheet_id: string | null;
  source_environment_sheet_id: string | null;
  source_prompt_set_id: string | null;
  source_voice_script_id: string | null;
  production_package_dir: string | null;
  image_manifest_path: string | null;
  source_asset_manifest_id: string | null;
  source_timeline_id: string | null;
  source_subtitle_plan_id: string | null;
  source_music_plan_id: string | null;
  source_editing_plan_id: string | null;
  source_thumbnail_plan_id: string | null;
  source_publishing_metadata_id: string | null;
  producer_package_dir: string | null;
  rendered_video_path: string | null;
}

/** Mirrors web_api/models.py's CreateProjectRequest - the body POST
 * /projects expects. Every field beyond `idea` is optional there too.
 *
 * scene_count_mode/scene_count implement the Custom Scene Count Override:
 * "default" (unchanged pre-existing behavior) leaves scene count to Director
 * Studio's own judgment (typically ~20-21 scenes); "custom" makes
 * scene_count a hard requirement the backend validates and the whole
 * pipeline must hit exactly - see SCENE_COUNT_MIN/SCENE_COUNT_MAX in
 * features/projects/NewProjectForm.tsx, which mirror config.py's
 * MIN_SCENE_COUNT/MAX_SCENE_COUNT. */
export interface CreateProjectRequest {
  idea: string;
  duration_seconds?: number;
  tone?: string | null;
  audience?: string | null;
  art_style?: string | null;
  skip_research?: boolean;
  scene_count_mode?: "default" | "custom";
  scene_count?: number | null;
}

/** Mirrors web_api/models.py's RenderRunRequest. All fields optional -
 * omitting the body entirely behaves like render_app.py with no flags. */
export interface RenderRunRequest {
  resolution?: string;
  fps?: number;
  video_codec?: string;
  audio_codec?: string;
  crf?: number;
  preset?: string;
  pix_fmt?: string;
  subtitle_mode?: string;
  dry_run?: boolean;
  timeout_seconds?: number | null;
}

/** Mirrors web_api/models.py's PublishRunRequest. */
export interface PublishRunRequest {
  platform?: string;
  dry_run?: boolean;
}

/** Structured error body every endpoint returns via HTTPException -
 * FastAPI's default {"detail": "..."} shape. */
export interface ApiErrorBody {
  detail?: string | { msg: string }[] | unknown;
}

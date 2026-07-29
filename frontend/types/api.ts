/** Mirrors web_api/models.py's CreateProjectRequest - the body POST
 * /projects expects. Every field beyond `idea` is optional there too. */
export interface CreateProjectRequest {
  idea: string;
  duration_seconds?: number;
  tone?: string | null;
  audience?: string | null;
  art_style?: string | null;
  skip_research?: boolean;
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

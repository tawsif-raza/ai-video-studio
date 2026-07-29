/**
 * Mirrors web_api/run_registry.py's RunStatus + Run models exactly.
 */
export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export interface Run {
  run_id: string;
  project_id: string;
  stage: string; // "director" | "producer" | "render" | "publish"
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

/** Mirrors web_api/models.py's RunAccepted - the 202 response body every
 * POST .../run endpoint returns. */
export interface RunAccepted {
  project_id: string;
  run_id: string;
  status: RunStatus;
}

/** Shared shape of RenderStatusResponse / PublishStatusResponse
 * (web_api/models.py) - identical fields except project_state, which only
 * the publish endpoint returns. */
export interface StageStatus {
  run_id: string;
  status: RunStatus;
  current_stage: string;
  progress: number;
  started_at: string;
  updated_at: string;
  error: string | null;
}

export interface PublishStageStatus extends StageStatus {
  project_state: string;
}

/**
 * Mirrors web_api/sse.py's _events_for() - the named SSE event types this
 * app's backend actually emits (Milestone W6), each with its own payload
 * shape. Not every event carries every field the Run model has; this is
 * intentionally narrower, matching exactly what the stream sends.
 */
export type RunStartedEvent = {
  run_id: string;
  project_id: string;
  type: string;
  status: RunStatus;
};
export type StageChangedEvent = { current_stage: string };
export type ProgressEvent = { progress: number };
export type CompletedEvent = { status: RunStatus };
export type FailedEvent = { status: RunStatus; error: string | null };

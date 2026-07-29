import { API_BASE_URL } from "@/api/client";

/** GET /runs/{id}/events (W6) */
export const runEventsUrl = (runId: string): string => `${API_BASE_URL}/runs/${runId}/events`;

/** GET /projects/{id}/events (W6) */
export const projectEventsUrl = (projectId: string): string =>
  `${API_BASE_URL}/projects/${projectId}/events`;

/** The exact named SSE event types web_api/sse.py's _events_for() emits -
 * kept in one place so the hook that calls addEventListener for each of
 * them can't drift from what the backend actually sends. */
export const RUN_EVENT_NAMES = [
  "run_started",
  "stage_changed",
  "progress",
  "completed",
  "failed",
] as const;

export type RunEventName = (typeof RUN_EVENT_NAMES)[number];

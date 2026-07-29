import { API_BASE_URL, apiGet, apiPost } from "@/api/client";
import type { PublishRunRequest, RenderRunRequest } from "@/types/api";
import type { PublishStageStatus, Run, RunAccepted, StageStatus } from "@/types/run";

/** GET /runs/{id} (W2) */
export const getRun = (runId: string): Promise<Run> => apiGet<Run>(`/runs/${runId}`);

/** POST /projects/{id}/producer/run (W3) - no body. */
export const runProducer = (projectId: string): Promise<RunAccepted> =>
  apiPost<RunAccepted>(`/projects/${projectId}/producer/run`);

/** POST /projects/{id}/render/run (W4). Body defaults mirror render_app.py's
 * own argparse defaults when omitted. */
export const runRender = (projectId: string, body: RenderRunRequest = {}): Promise<RunAccepted> =>
  apiPost<RunAccepted>(`/projects/${projectId}/render/run`, body);

/** GET /projects/{id}/render/status (W4) */
export const getRenderStatus = (projectId: string): Promise<StageStatus> =>
  apiGet<StageStatus>(`/projects/${projectId}/render/status`);

/** GET /projects/{id}/render/video (W8) - not a JSON fetch call, just the
 * URL a <video> element's src should point at directly. Never a
 * filesystem path - the real one only ever exists server-side. */
export const renderVideoUrl = (projectId: string): string => `${API_BASE_URL}/projects/${projectId}/render/video`;

/** POST /projects/{id}/publish/run (W5). */
export const runPublish = (projectId: string, body: PublishRunRequest = {}): Promise<RunAccepted> =>
  apiPost<RunAccepted>(`/projects/${projectId}/publish/run`, body);

/** GET /projects/{id}/publish/status (W5) */
export const getPublishStatus = (projectId: string): Promise<PublishStageStatus> =>
  apiGet<PublishStageStatus>(`/projects/${projectId}/publish/status`);

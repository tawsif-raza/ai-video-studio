import { apiDelete, apiGet, apiPost, apiPostForm, apiPostFormWithProgress } from "@/api/client";
import type { CreateProjectRequest } from "@/types/api";
import type {
  BulkMediaDeleteResponse,
  ImportedMediaManifest,
  MediaCategory,
  MediaDeleteItem,
  MediaUploadResponse,
} from "@/types/media";
import type { Project } from "@/types/project";
import type { RunAccepted } from "@/types/run";

/** GET /projects (W1) */
export const listProjects = (): Promise<Project[]> => apiGet<Project[]>("/projects");

/** GET /projects/{id} (W1) */
export const getProject = (projectId: string): Promise<Project> =>
  apiGet<Project>(`/projects/${projectId}`);

/** DELETE /projects/{id} (W1) */
export const deleteProject = (projectId: string): Promise<void> =>
  apiDelete<void>(`/projects/${projectId}`);

/** POST /projects (W2) - creates a project AND starts a Director Studio
 * run in one call; returns a Run envelope (202), not the Project itself. */
export const createProject = (body: CreateProjectRequest): Promise<RunAccepted> =>
  apiPost<RunAccepted>("/projects", body);

/** GET /projects/{id}/media (W3) */
export const getProjectMedia = (projectId: string): Promise<ImportedMediaManifest> =>
  apiGet<ImportedMediaManifest>(`/projects/${projectId}/media`);

/** POST /projects/{id}/media (W3) - one file per call, exactly as the
 * backend expects. */
export const uploadMedia = (projectId: string, file: File): Promise<MediaUploadResponse> => {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<MediaUploadResponse>(`/projects/${projectId}/media`, form);
};

/** POST /projects/{id}/media (W10) - same endpoint as uploadMedia, via
 * XMLHttpRequest so onProgress can report bytes-sent as the upload streams,
 * for the dashboard's per-file progress bar. */
export const uploadMediaWithProgress = (
  projectId: string,
  file: File,
  onProgress?: (loadedBytes: number, totalBytes: number) => void,
): Promise<MediaUploadResponse> => {
  const form = new FormData();
  form.append("file", file);
  return apiPostFormWithProgress<MediaUploadResponse>(`/projects/${projectId}/media`, form, onProgress);
};

/** DELETE /projects/{id}/media/{category}/{filename} (W10) */
export const deleteMedia = (projectId: string, category: MediaCategory, filename: string): Promise<void> =>
  apiDelete<void>(`/projects/${projectId}/media/${category}/${encodeURIComponent(filename)}`);

/** POST /projects/{id}/media/bulk-delete (W10) - one call for a multi-select
 * "delete selected" action; the backend reports each item's outcome
 * individually rather than failing the whole batch on one missing file. */
export const bulkDeleteMedia = (projectId: string, items: MediaDeleteItem[]): Promise<BulkMediaDeleteResponse> =>
  apiPost<BulkMediaDeleteResponse>(`/projects/${projectId}/media/bulk-delete`, { items });

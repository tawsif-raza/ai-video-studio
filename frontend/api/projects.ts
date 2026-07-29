import { apiDelete, apiGet, apiPost, apiPostForm } from "@/api/client";
import type { CreateProjectRequest } from "@/types/api";
import type { ImportedMediaManifest, MediaUploadResponse } from "@/types/media";
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

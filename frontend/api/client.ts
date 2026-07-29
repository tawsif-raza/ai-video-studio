import type { ApiErrorBody } from "@/types/api";

/**
 * Single place that knows the backend's base URL - every other module in
 * this app goes through here, never calls fetch()/EventSource directly.
 * Mirrors WEB_DASHBOARD_ARCHITECTURE.md SS8.2's lib/api-client.ts intent.
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function extractErrorMessage(status: number, body: ApiErrorBody | null): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === "object" && d && "msg" in d ? d.msg : String(d))).join("; ");
    }
  }
  return `Request failed with status ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    // Every W1-W6 endpoint is either a live snapshot (GET) or a
    // state-changing action (POST/DELETE) - nothing here should ever be
    // served from Next.js's fetch cache (relevant in `next build`/`next
    // start`, not just dev - see Next 16's "auto no cache" default).
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, extractErrorMessage(response.status, body), body);
  }

  return body as T;
}

export const apiGet = <T>(path: string): Promise<T> => request<T>(path, { method: "GET" });

export const apiPost = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const apiPostForm = <T>(path: string, form: FormData): Promise<T> =>
  request<T>(path, { method: "POST", body: form });

export const apiDelete = <T>(path: string): Promise<T> => request<T>(path, { method: "DELETE" });

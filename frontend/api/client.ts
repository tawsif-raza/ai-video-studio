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

/**
 * Milestone W10: fetch() has no upload-progress signal (its ReadableStream
 * request-body path isn't supported widely/consistently enough for a byte-
 * accurate progress bar), so a multipart upload that needs to report
 * "N% sent" has to go through XMLHttpRequest instead - the one place in
 * this app that doesn't go through request() above. Mirrors request()'s
 * error handling (ApiError with parsed JSON body when possible) and its
 * "no fetch cache" intent (XHR doesn't participate in the fetch cache at
 * all, so there's nothing to opt out of).
 */
export function apiPostFormWithProgress<T>(
  path: string,
  form: FormData,
  onProgress?: (loadedBytes: number, totalBytes: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    xhr.responseType = "text";

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(event.loaded, event.total);
        }
      };
    }

    xhr.onerror = () => reject(new ApiError(0, "Network error during upload", null));
    xhr.onabort = () => reject(new ApiError(0, "Upload aborted", null));

    xhr.onload = () => {
      const contentType = xhr.getResponseHeader("content-type") ?? "";
      let body: unknown = null;
      if (contentType.includes("application/json") && xhr.responseText) {
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          body = null;
        }
      }

      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(xhr.status, extractErrorMessage(xhr.status, body as ApiErrorBody | null), body));
        return;
      }

      resolve(body as T);
    };

    xhr.send(form);
  });
}

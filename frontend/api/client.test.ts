import { afterEach, describe, expect, it, vi } from "vitest";

import { apiDelete, apiGet, apiPost, apiPostForm, apiPostFormWithProgress, ApiError } from "./client";

/**
 * jsdom's real XMLHttpRequest would attempt an actual network request, so
 * apiPostFormWithProgress's XHR path needs a hand-rolled fake the same way
 * every other test here mocks fetch - open/send capture the call, and the
 * test drives upload.onprogress/onload/onerror manually to simulate the
 * browser's event timing.
 */
class FakeXHR {
  static instances: FakeXHR[] = [];
  method = "";
  url = "";
  status = 200;
  responseText = "";
  responseHeaders: Record<string, string> = {};
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  responseType = "";
  sentBody: unknown = null;

  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }

  getResponseHeader(name: string): string | null {
    return this.responseHeaders[name.toLowerCase()] ?? null;
  }

  send(body: unknown) {
    this.sentBody = body;
    FakeXHR.instances.push(this);
  }
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    FakeXHR.instances = [];
  });

  it("apiGet issues a GET request and returns parsed JSON", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ ok: true }));

    const result = await apiGet<{ ok: boolean }>("/projects");

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects");
    expect(init?.method).toBe("GET");
    expect(init?.cache).toBe("no-store");
  });

  it("apiPost sends a JSON body with the right content-type header", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ run_id: "abc" }));

    await apiPost("/projects/p1/producer/run", { platform: "youtube" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ platform: "youtube" }));
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("apiPost with no body omits the body and content-type header", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ run_id: "abc" }));

    await apiPost("/projects/p1/producer/run");

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.body).toBeUndefined();
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("apiPostForm sends a FormData body without a JSON content-type header", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ filename: "a.png" }));
    const form = new FormData();
    form.append("file", new File(["x"], "a.png"));

    await apiPostForm("/projects/p1/media", form);

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.body).toBe(form);
    expect((init?.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("apiDelete issues a DELETE and returns undefined for a 204", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 204 }));

    const result = await apiDelete("/projects/p1");

    expect(result).toBeUndefined();
  });

  it("throws ApiError with the backend's detail message on a non-2xx response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Project p1 not found" }, { status: 404, statusText: "Not Found" }),
    );

    await expect(apiGet("/projects/p1")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Project p1 not found",
    });
  });

  it("ApiError falls back to a generic message when detail is missing", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 500 }));

    let caught: unknown;
    try {
      await apiGet("/projects");
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).message).toBe("Request failed with status 500");
  });

  it("extracts a joined message from FastAPI's validation-error array shape", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse(
        { detail: [{ msg: "field required" }, { msg: "must be a string" }] },
        { status: 422 },
      ),
    );

    await expect(apiGet("/projects")).rejects.toMatchObject({
      status: 422,
      message: "field required; must be a string",
    });
  });
});

describe("apiPostFormWithProgress", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeXHR.instances = [];
  });

  it("opens a POST XHR to the right URL and sends the form as the body", () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const form = new FormData();
    form.append("file", new File(["x"], "shot1.png"));

    apiPostFormWithProgress("/projects/p1/media", form);

    const xhr = FakeXHR.instances[0];
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("http://127.0.0.1:8000/projects/p1/media");
    expect(xhr.sentBody).toBe(form);
  });

  it("reports upload progress via onProgress as lengthComputable events fire", () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const onProgress = vi.fn();

    apiPostFormWithProgress("/projects/p1/media", new FormData(), onProgress);

    const xhr = FakeXHR.instances[0];
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 200 } as ProgressEvent);
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 200, total: 200 } as ProgressEvent);

    expect(onProgress).toHaveBeenNthCalledWith(1, 50, 200);
    expect(onProgress).toHaveBeenNthCalledWith(2, 200, 200);
  });

  it("ignores non-lengthComputable progress events", () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const onProgress = vi.fn();

    apiPostFormWithProgress("/projects/p1/media", new FormData(), onProgress);

    FakeXHR.instances[0].upload.onprogress?.({ lengthComputable: false, loaded: 1, total: 0 } as ProgressEvent);

    expect(onProgress).not.toHaveBeenCalled();
  });

  it("resolves with the parsed JSON body on a successful response", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);

    const promise = apiPostFormWithProgress<{ filename: string }>("/projects/p1/media", new FormData());
    const xhr = FakeXHR.instances[0];
    xhr.status = 201;
    xhr.responseHeaders["content-type"] = "application/json";
    xhr.responseText = JSON.stringify({ filename: "shot1.png" });
    xhr.onload?.();

    await expect(promise).resolves.toEqual({ filename: "shot1.png" });
  });

  it("rejects with ApiError carrying the backend's detail on a non-2xx status", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);

    const promise = apiPostFormWithProgress("/projects/p1/media", new FormData());
    const xhr = FakeXHR.instances[0];
    xhr.status = 400;
    xhr.responseHeaders["content-type"] = "application/json";
    xhr.responseText = JSON.stringify({ detail: "Unsupported media file extension" });
    xhr.onload?.();

    await expect(promise).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "Unsupported media file extension",
    });
  });

  it("rejects with ApiError on a network error", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXHR);

    const promise = apiPostFormWithProgress("/projects/p1/media", new FormData());
    FakeXHR.instances[0].onerror?.();

    await expect(promise).rejects.toMatchObject({ name: "ApiError", status: 0 });
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

import { apiDelete, apiGet, apiPost, apiPostForm, ApiError } from "./client";

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

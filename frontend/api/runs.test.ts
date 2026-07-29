import { afterEach, describe, expect, it, vi } from "vitest";

import { getPublishStatus, getRenderStatus, getRun, renderVideoUrl, runProducer, runPublish, runRender } from "./runs";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("runs api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("getRun calls GET /runs/{id}", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ run_id: "r1" }));

    await getRun("r1");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8000/runs/r1");
  });

  it("runProducer POSTs to /projects/{id}/producer/run with no body", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ project_id: "p1", run_id: "r1", status: "queued" }));

    await runProducer("p1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/producer/run");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
  });

  it("runRender POSTs to /projects/{id}/render/run with an empty body by default", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ project_id: "p1", run_id: "r1", status: "queued" }));

    await runRender("p1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/render/run");
    expect(JSON.parse(init?.body as string)).toEqual({});
  });

  it("runRender forwards render options in the body", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ project_id: "p1", run_id: "r1", status: "queued" }));

    await runRender("p1", { resolution: "1280x720", dry_run: true });

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual({ resolution: "1280x720", dry_run: true });
  });

  it("getRenderStatus calls GET /projects/{id}/render/status", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({
        run_id: "r1",
        status: "succeeded",
        current_stage: "completed",
        progress: 100,
        started_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:01Z",
        error: null,
      }),
    );

    await getRenderStatus("p1");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8000/projects/p1/render/status");
  });

  it("runPublish POSTs to /projects/{id}/publish/run with the platform in the body", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ project_id: "p1", run_id: "r1", status: "queued" }));

    await runPublish("p1", { platform: "youtube" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/publish/run");
    expect(JSON.parse(init?.body as string)).toEqual({ platform: "youtube" });
  });

  it("getPublishStatus calls GET /projects/{id}/publish/status", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({
        run_id: "r1",
        status: "succeeded",
        current_stage: "completed",
        progress: 100,
        started_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:01Z",
        error: null,
        project_state: "VIDEO_RENDERED",
      }),
    );

    await getPublishStatus("p1");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8000/projects/p1/publish/status");
  });

  it("renderVideoUrl builds the GET /projects/{id}/render/video URL without fetching", () => {
    const fetchMock = vi.spyOn(global, "fetch");

    const url = renderVideoUrl("p1");

    expect(url).toBe("http://127.0.0.1:8000/projects/p1/render/video");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

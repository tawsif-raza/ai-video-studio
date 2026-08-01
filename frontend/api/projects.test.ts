import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bulkDeleteMedia,
  createProject,
  deleteMedia,
  deleteProject,
  getProject,
  getProjectMedia,
  listProjects,
  uploadMedia,
} from "./projects";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("projects api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("listProjects calls GET /projects", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse([]));

    await listProjects();

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects");
    expect(init?.method).toBe("GET");
  });

  it("getProject calls GET /projects/{id}", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ project_id: "p1" }));

    await getProject("p1");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8000/projects/p1");
  });

  it("deleteProject calls DELETE /projects/{id}", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 204 }));

    await deleteProject("p1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1");
    expect(init?.method).toBe("DELETE");
  });

  it("createProject POSTs the create-project body to /projects", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ project_id: "p1", run_id: "r1", status: "queued" }));

    const result = await createProject({ idea: "A lighthouse keeper", duration_seconds: 30 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ idea: "A lighthouse keeper", duration_seconds: 30 });
    expect(result).toEqual({ project_id: "p1", run_id: "r1", status: "queued" });
  });

  it("getProjectMedia calls GET /projects/{id}/media", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ images: [], videos: [], audio: [] }));

    await getProjectMedia("p1");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8000/projects/p1/media");
  });

  it("uploadMedia POSTs a single-file FormData to /projects/{id}/media", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(jsonResponse({ filename: "shot1.png", path: "/x/shot1.png", size_bytes: 10 }));
    const file = new File(["x"], "shot1.png", { type: "image/png" });

    await uploadMedia("p1", file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/media");
    expect(init?.method).toBe("POST");
    const form = init?.body as FormData;
    expect(form.get("file")).toBe(file);
  });

  it("deleteMedia calls DELETE /projects/{id}/media/{category}/{filename}", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 204 }));

    await deleteMedia("p1", "images", "shot1.png");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/media/images/shot1.png");
    expect(init?.method).toBe("DELETE");
  });

  it("deleteMedia URL-encodes the filename", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 204 }));

    await deleteMedia("p1", "images", "shot 1.png");

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/media/images/shot%201.png");
  });

  it("bulkDeleteMedia POSTs the item list to /projects/{id}/media/bulk-delete", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ results: [] }));

    const result = await bulkDeleteMedia("p1", [
      { category: "images", filename: "shot1.png" },
      { category: "video", filename: "clip1.mp4" },
    ]);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/media/bulk-delete");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      items: [
        { category: "images", filename: "shot1.png" },
        { category: "video", filename: "clip1.mp4" },
      ],
    });
    expect(result).toEqual({ results: [] });
  });
});

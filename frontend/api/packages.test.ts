import { afterEach, describe, expect, it, vi } from "vitest";

import { getProducerPackage, getProductionPackage } from "./packages";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("packages api", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("getProductionPackage calls GET /projects/{id}/production-package", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ "manifest.json": {} }));

    await getProductionPackage("p1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://127.0.0.1:8000/projects/p1/production-package");
    expect(init?.method).toBe("GET");
  });

  it("getProducerPackage calls GET /projects/{id}/producer-package", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(jsonResponse({ "manifest.json": {} }));

    await getProducerPackage("p1");

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://127.0.0.1:8000/projects/p1/producer-package");
  });

  it("propagates a 404 as an ApiError when the package doesn't exist yet", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      jsonResponse({ detail: "Production package not yet generated for project p1" }, { status: 404 }),
    );

    await expect(getProductionPackage("p1")).rejects.toMatchObject({ status: 404 });
  });
});

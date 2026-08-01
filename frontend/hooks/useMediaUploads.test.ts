import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as projectsApi from "@/api/projects";

import { useMediaUploads } from "./useMediaUploads";

vi.mock("@/api/projects", () => ({
  uploadMediaWithProgress: vi.fn(),
}));

const uploadMediaWithProgress = vi.mocked(projectsApi.uploadMediaWithProgress);

function makeFile(name: string, size = 100): File {
  return new File([new Uint8Array(size)], name, { type: "image/png" });
}

describe("useMediaUploads", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("never runs more than `concurrency` uploads at once", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const resolvers: Array<() => void> = [];

    uploadMediaWithProgress.mockImplementation((_projectId, file) => {
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      return new Promise((resolve) => {
        resolvers.push(() => {
          inFlight--;
          resolve({ filename: file.name, path: `/x/${file.name}`, size_bytes: file.size });
        });
      });
    });

    const { result } = renderHook(() => useMediaUploads("p1", 2));
    const files = Array.from({ length: 5 }, (_, i) => makeFile(`f${i}.png`));

    let uploadPromise: Promise<{ succeeded: number; failed: number }>;
    act(() => {
      uploadPromise = result.current.startUpload(files);
    });

    // Only the concurrency limit's worth of workers should have started.
    await waitFor(() => expect(uploadMediaWithProgress).toHaveBeenCalledTimes(2));
    expect(inFlight).toBe(2);

    // Resolve one - a third upload should start to take its place, still
    // never exceeding the configured limit of 2 in flight at once.
    act(() => resolvers[0]());
    await waitFor(() => expect(uploadMediaWithProgress).toHaveBeenCalledTimes(3));
    expect(inFlight).toBeLessThanOrEqual(2);

    // Drain the rest.
    while (resolvers.length > 0) {
      const next = resolvers.shift();
      act(() => next?.());
      // eslint-disable-next-line no-await-in-loop
      await waitFor(() => expect(uploadMediaWithProgress.mock.calls.length).toBeGreaterThanOrEqual(1));
    }

    await act(async () => {
      await uploadPromise;
    });

    expect(uploadMediaWithProgress).toHaveBeenCalledTimes(5);
    expect(maxInFlight).toBeLessThanOrEqual(2);
    expect(result.current.uploads.every((item) => item.status === "done")).toBe(true);
  });

  it("continues past a failed file and reports succeeded/failed counts", async () => {
    uploadMediaWithProgress.mockImplementation(async (_projectId, file) => {
      if (file.name === "bad.png") throw new Error("rejected");
      return { filename: file.name, path: `/x/${file.name}`, size_bytes: file.size };
    });

    const { result } = renderHook(() => useMediaUploads("p1", 4));
    const files = [makeFile("good1.png"), makeFile("bad.png"), makeFile("good2.png")];

    let outcome: { succeeded: number; failed: number } | undefined;
    await act(async () => {
      outcome = await result.current.startUpload(files);
    });

    expect(outcome).toEqual({ succeeded: 2, failed: 1 });
    const badItem = result.current.uploads.find((item) => item.name === "bad.png");
    expect(badItem?.status).toBe("error");
    expect(badItem?.error).toBe("rejected");
  });

  it("reports per-file and overall progress as uploads report bytes sent", async () => {
    uploadMediaWithProgress.mockImplementation(async (_projectId, file, onProgress) => {
      onProgress?.(file.size / 2, file.size);
      onProgress?.(file.size, file.size);
      return { filename: file.name, path: `/x/${file.name}`, size_bytes: file.size };
    });

    const { result } = renderHook(() => useMediaUploads("p1", 4));
    const files = [makeFile("a.png", 100), makeFile("b.png", 200)];

    await act(async () => {
      await result.current.startUpload(files);
    });

    expect(result.current.overallProgress).toEqual({ loaded: 300, total: 300 });
  });

  it("clearUploads resets the upload list and progress", async () => {
    uploadMediaWithProgress.mockResolvedValue({ filename: "a.png", path: "/x/a.png", size_bytes: 100 });

    const { result } = renderHook(() => useMediaUploads("p1", 4));
    await act(async () => {
      await result.current.startUpload([makeFile("a.png", 100)]);
    });
    expect(result.current.uploads).toHaveLength(1);

    act(() => result.current.clearUploads());

    expect(result.current.uploads).toHaveLength(0);
    expect(result.current.overallProgress).toEqual({ loaded: 0, total: 0 });
  });
});

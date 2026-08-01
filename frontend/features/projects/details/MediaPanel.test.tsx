import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as projectsApi from "@/api/projects";
import type { BulkMediaDeleteResponse, ImportedMediaManifest, MediaUploadResponse } from "@/types/media";

import { MediaPanel } from "./MediaPanel";

vi.mock("@/api/projects", () => ({
  getProjectMedia: vi.fn(),
  uploadMediaWithProgress: vi.fn(),
  deleteMedia: vi.fn(),
  bulkDeleteMedia: vi.fn(),
}));

const getProjectMedia = vi.mocked(projectsApi.getProjectMedia);
const uploadMediaWithProgress = vi.mocked(projectsApi.uploadMediaWithProgress);
const deleteMedia = vi.mocked(projectsApi.deleteMedia);
const bulkDeleteMedia = vi.mocked(projectsApi.bulkDeleteMedia);

function manifest(overrides: Partial<ImportedMediaManifest> = {}): ImportedMediaManifest {
  return {
    images: [
      { filename: "scene_1_shot_1.png", path: "/x/scene_1_shot_1.png", size_bytes: 1000, sha256: "a".repeat(64) },
      { filename: "scene_1_shot_2.png", path: "/x/scene_1_shot_2.png", size_bytes: 2000, sha256: "b".repeat(64) },
    ],
    videos: [],
    audio: [],
    ...overrides,
  };
}

describe("MediaPanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("loads and displays the media manifest grouped by category", async () => {
    getProjectMedia.mockResolvedValue(manifest());

    render(<MediaPanel projectId="p1" />);

    expect(await screen.findByText("scene_1_shot_1.png", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("scene_1_shot_2.png", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("2 total file(s)")).toBeInTheDocument();
  });

  it("Select All and Clear Selection update the selected count", async () => {
    getProjectMedia.mockResolvedValue(manifest());
    const user = userEvent.setup();

    render(<MediaPanel projectId="p1" />);
    await screen.findByText("scene_1_shot_1.png", { exact: false });

    await user.click(screen.getByRole("button", { name: "Select All" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear Selection" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("deletes a single file after confirmation and refreshes the manifest", async () => {
    getProjectMedia.mockResolvedValueOnce(manifest()).mockResolvedValueOnce(
      manifest({
        images: [
          { filename: "scene_1_shot_2.png", path: "/x/scene_1_shot_2.png", size_bytes: 2000, sha256: "b".repeat(64) },
        ],
      }),
    );
    deleteMedia.mockResolvedValue(undefined);
    const onMediaChanged = vi.fn();
    const user = userEvent.setup();

    render(<MediaPanel projectId="p1" onMediaChanged={onMediaChanged} />);
    await screen.findByText("scene_1_shot_1.png", { exact: false });

    await user.click(screen.getByRole("button", { name: "Delete scene_1_shot_1.png" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(deleteMedia).toHaveBeenCalledWith("p1", "images", "scene_1_shot_1.png"));
    await waitFor(() => expect(screen.queryByText("scene_1_shot_1.png", { exact: false })).not.toBeInTheDocument());
    expect(onMediaChanged).toHaveBeenCalled();
  });

  it("cancelling the single-delete dialog does not call deleteMedia", async () => {
    getProjectMedia.mockResolvedValue(manifest());
    const user = userEvent.setup();

    render(<MediaPanel projectId="p1" />);
    await screen.findByText("scene_1_shot_1.png", { exact: false });

    await user.click(screen.getByRole("button", { name: "Delete scene_1_shot_1.png" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(deleteMedia).not.toHaveBeenCalled();
  });

  it("shows an error message when a single delete fails", async () => {
    getProjectMedia.mockResolvedValue(manifest());
    deleteMedia.mockRejectedValue(new Error("file is locked"));
    const user = userEvent.setup();

    render(<MediaPanel projectId="p1" />);
    await screen.findByText("scene_1_shot_1.png", { exact: false });

    await user.click(screen.getByRole("button", { name: "Delete scene_1_shot_1.png" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("file is locked")).toBeInTheDocument();
  });

  it("bulk-deletes selected files and reports partial failures individually", async () => {
    getProjectMedia.mockResolvedValueOnce(manifest()).mockResolvedValueOnce(manifest({ images: [] }));
    const bulkResponse: BulkMediaDeleteResponse = {
      results: [
        { category: "images", filename: "scene_1_shot_1.png", success: true },
        { category: "images", filename: "scene_1_shot_2.png", success: false, error: "not found" },
      ],
    };
    bulkDeleteMedia.mockResolvedValue(bulkResponse);
    const onMediaChanged = vi.fn();
    const user = userEvent.setup();

    render(<MediaPanel projectId="p1" onMediaChanged={onMediaChanged} />);
    await screen.findByText("scene_1_shot_1.png", { exact: false });

    await user.click(screen.getByRole("button", { name: "Select All" }));
    await user.click(screen.getByRole("button", { name: "Delete Selected" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(bulkDeleteMedia).toHaveBeenCalledWith("p1", [
        { category: "images", filename: "scene_1_shot_1.png" },
        { category: "images", filename: "scene_1_shot_2.png" },
      ]),
    );
    expect(await screen.findByText(/1 of 2 file\(s\) could not be deleted/)).toBeInTheDocument();
    expect(onMediaChanged).toHaveBeenCalled();
  });

  it("uploads multiple files concurrently, shows progress, and refreshes after completion", async () => {
    getProjectMedia.mockResolvedValueOnce(manifest({ images: [], videos: [], audio: [] })).mockResolvedValueOnce(
      manifest(),
    );
    uploadMediaWithProgress.mockImplementation(async (_projectId, file, onProgress) => {
      onProgress?.(file.size, file.size);
      return { filename: file.name, path: `/x/${file.name}`, size_bytes: file.size } satisfies MediaUploadResponse;
    });
    const onMediaChanged = vi.fn();
    const user = userEvent.setup();

    const { container } = render(<MediaPanel projectId="p1" onMediaChanged={onMediaChanged} />);
    await waitFor(() => expect(screen.getByText("0 total file(s)")).toBeInTheDocument());

    const fileA = new File(["a"], "scene_1_shot_1.png", { type: "image/png" });
    const fileB = new File(["b"], "scene_1_shot_2.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, [fileA, fileB]);
    await user.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(uploadMediaWithProgress).toHaveBeenCalledTimes(2));
    expect(uploadMediaWithProgress.mock.calls[0][0]).toBe("p1");
    await waitFor(() => expect(onMediaChanged).toHaveBeenCalled());
    // Two matches expected: the refreshed Images section, and the upload
    // progress list (which intentionally keeps showing completed uploads
    // until "Clear Upload List" is clicked).
    await waitFor(() =>
      expect(screen.getAllByText("scene_1_shot_1.png", { exact: false }).length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getByText("2 total file(s)")).toBeInTheDocument();
  });

  it("continues uploading remaining files when one upload fails, reporting the failure count", async () => {
    getProjectMedia.mockResolvedValue(manifest({ images: [], videos: [], audio: [] }));
    uploadMediaWithProgress.mockImplementation(async (_projectId, file) => {
      if (file.name === "bad.png") throw new Error("Unsupported media file extension");
      return { filename: file.name, path: `/x/${file.name}`, size_bytes: file.size } satisfies MediaUploadResponse;
    });
    const user = userEvent.setup();

    const { container } = render(<MediaPanel projectId="p1" />);
    await waitFor(() => expect(screen.getByText("0 total file(s)")).toBeInTheDocument());

    const good = new File(["a"], "good.png", { type: "image/png" });
    const bad = new File(["b"], "bad.png", { type: "image/png" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, [good, bad]);
    await user.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(uploadMediaWithProgress).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/1 of 2 file\(s\) failed to upload/)).toBeInTheDocument();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Project } from "@/types/project";

const {
  useProjectMock,
  useStageSnapshotsMock,
  useProductionPackageMock,
  useProducerPackageMock,
} = vi.hoisted(() => ({
  useProjectMock: vi.fn(),
  useStageSnapshotsMock: vi.fn(),
  useProductionPackageMock: vi.fn(),
  useProducerPackageMock: vi.fn(),
}));

vi.mock("@/hooks/useProject", () => ({ useProject: useProjectMock }));
vi.mock("@/hooks/useStageSnapshots", () => ({ useStageSnapshots: useStageSnapshotsMock }));
vi.mock("@/hooks/useProductionPackage", () => ({ useProductionPackage: useProductionPackageMock }));
vi.mock("@/hooks/useProducerPackage", () => ({ useProducerPackage: useProducerPackageMock }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

import { ProjectWorkspace } from "./ProjectWorkspace";

const PROJECT_ID = "11111111-1111-1111-1111-111111111111";

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    project_id: PROJECT_ID,
    status: "EDIT_PLAN_READY",
    created_at: "2026-01-01T00:00:00Z",
    source_research_brief_id: null,
    source_plan_id: null,
    source_storyboard_id: null,
    source_shot_plan_id: null,
    source_camera_plan_id: null,
    source_character_sheet_id: null,
    source_environment_sheet_id: null,
    source_prompt_set_id: null,
    source_voice_script_id: null,
    production_package_dir: null,
    image_manifest_path: null,
    source_asset_manifest_id: null,
    source_timeline_id: null,
    source_subtitle_plan_id: null,
    source_music_plan_id: null,
    source_editing_plan_id: null,
    source_thumbnail_plan_id: null,
    source_publishing_metadata_id: null,
    producer_package_dir: null,
    rendered_video_path: null,
    ...overrides,
  };
}

describe("ProjectWorkspace", () => {
  beforeEach(() => {
    useProjectMock.mockReset();
    useStageSnapshotsMock.mockReset();
    useProductionPackageMock.mockReset();
    useProducerPackageMock.mockReset();

    useProjectMock.mockReturnValue({ project: makeProject(), isLoading: false, error: null, refetch: vi.fn() });
    useStageSnapshotsMock.mockReturnValue({ render: null, publish: null, isLoading: false });
    useProductionPackageMock.mockReturnValue({ productionPackage: null, isLoading: false, error: null });
    useProducerPackageMock.mockReturnValue({ producerPackage: null, isLoading: false, error: null });
  });

  it("shows a loading message while the project is loading", () => {
    useProjectMock.mockReturnValue({ project: null, isLoading: true, error: null, refetch: vi.fn() });

    render(<ProjectWorkspace projectId={PROJECT_ID} />);

    expect(screen.getByText(/loading project/i)).toBeInTheDocument();
  });

  it("shows an error message when the project fails to load", () => {
    useProjectMock.mockReturnValue({ project: null, isLoading: false, error: "not found", refetch: vi.fn() });

    render(<ProjectWorkspace projectId={PROJECT_ID} />);

    expect(screen.getByText(/failed to load project/i)).toBeInTheDocument();
  });

  it("loads correctly and defaults to the Overview tab", () => {
    render(<ProjectWorkspace projectId={PROJECT_ID} />);

    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Run Controls")).toBeInTheDocument();
    expect(screen.getByText(PROJECT_ID)).toBeInTheDocument();
  });

  it("switches to the Research tab and renders its (empty) content", () => {
    render(<ProjectWorkspace projectId={PROJECT_ID} />);

    fireEvent.click(screen.getByRole("tab", { name: "Research" }));

    expect(screen.getByRole("tab", { name: "Research" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/production package not generated yet/i)).toBeInTheDocument();
  });

  it("switches to the Timeline tab and renders producer-package content", () => {
    useProducerPackageMock.mockReturnValue({
      producerPackage: {
        "manifest.json": { package_id: "p1", files: [] },
        "timeline_plan.json": {
          timeline_id: "t1", source_asset_manifest_id: "a1", clips: [], voice_segments: [],
          total_duration_seconds: 42, generated_at: "2026-01-01T00:00:00Z",
        },
      },
      isLoading: false,
      error: null,
    });

    render(<ProjectWorkspace projectId={PROJECT_ID} />);
    fireEvent.click(screen.getByRole("tab", { name: "Timeline" }));

    expect(screen.getByText("42s")).toBeInTheDocument();
  });

  it("switches to the Render Preview tab and shows the empty state for a non-rendered project", () => {
    render(<ProjectWorkspace projectId={PROJECT_ID} />);

    fireEvent.click(screen.getByRole("tab", { name: "Render Preview" }));

    expect(screen.getByText(/no rendered video yet/i)).toBeInTheDocument();
  });

  it("switches to the Render Preview tab and shows a video element for a rendered project", () => {
    useProjectMock.mockReturnValue({
      project: makeProject({ status: "VIDEO_RENDERED", rendered_video_path: "/server/path/video.mp4" }),
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<ProjectWorkspace projectId={PROJECT_ID} />);
    fireEvent.click(screen.getByRole("tab", { name: "Render Preview" }));

    const video = container.querySelector("video");
    expect(video?.getAttribute("src")).toBe(`http://127.0.0.1:8000/projects/${PROJECT_ID}/render/video`);
  });

  it("switches to the Media tab", () => {
    render(<ProjectWorkspace projectId={PROJECT_ID} />);

    fireEvent.click(screen.getByRole("tab", { name: "Media" }));

    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });
});

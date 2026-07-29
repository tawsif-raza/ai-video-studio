import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Project } from "@/types/project";

import { RenderPreviewTab } from "./RenderPreviewTab";

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    project_id: "11111111-1111-1111-1111-111111111111",
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

describe("RenderPreviewTab", () => {
  it("shows an empty state when the project has no rendered video yet", () => {
    render(<RenderPreviewTab project={makeProject({ status: "EDIT_PLAN_READY" })} />);

    expect(screen.getByText(/no rendered video yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("application")).not.toBeInTheDocument(); // no <video> rendered
  });

  it("renders a video element pointed at the render/video endpoint URL, never a filesystem path", () => {
    const project = makeProject({
      status: "VIDEO_RENDERED",
      rendered_video_path: "D:\\ai_video_studio\\ai_video_studio\\outputs\\projects\\11111111-1111-1111-1111-111111111111\\renders\\video.mp4",
    });

    const { container } = render(<RenderPreviewTab project={project} />);

    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.getAttribute("src")).toBe(
      "http://127.0.0.1:8000/projects/11111111-1111-1111-1111-111111111111/render/video",
    );
    expect(video?.getAttribute("src")).not.toContain("D:\\");
    expect(video?.hasAttribute("controls")).toBe(true);
  });
});

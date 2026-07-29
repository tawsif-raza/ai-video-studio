import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectCard } from "./ProjectCard";
import type { Project } from "@/types/project";

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    project_id: "11111111-1111-1111-1111-111111111111",
    status: "PACKAGE_READY",
    created_at: "2026-01-15T10:30:00Z",
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

describe("ProjectCard", () => {
  it("shows the project id as the identifier (the backend has no name field)", () => {
    render(<ProjectCard project={makeProject()} />);
    expect(screen.getByText("11111111-1111-1111-1111-111111111111")).toBeInTheDocument();
  });

  it("shows the current ProjectState", () => {
    render(<ProjectCard project={makeProject({ status: "VIDEO_RENDERED" })} />);
    expect(screen.getByText("VIDEO RENDERED")).toBeInTheDocument();
  });

  it("shows an Open link to the project's detail page", () => {
    render(<ProjectCard project={makeProject()} />);
    const link = screen.getByRole("link", { name: "Open" });
    expect(link).toHaveAttribute("href", "/projects/11111111-1111-1111-1111-111111111111");
  });

  it("labels the timestamp 'Created' rather than overclaiming 'Last updated'", () => {
    render(<ProjectCard project={makeProject()} />);
    expect(screen.getByText(/^Created /)).toBeInTheDocument();
  });
});

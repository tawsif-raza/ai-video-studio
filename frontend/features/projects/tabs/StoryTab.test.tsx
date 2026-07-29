import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProductionPackage } from "@/types/package";

import { StoryTab } from "./StoryTab";

function makePackage(storyMarkdown: string): ProductionPackage {
  return {
    "manifest.json": { package_id: "p1", files: [] },
    "metadata.json": {
      package_id: "p1", source_plan_id: "", source_storyboard_id: "", generated_at: "",
      target_duration_seconds: 30, tone: null, audience: null, art_style: null,
    },
    "research_brief.json": { status: "skipped", reason: "skipped" },
    "story.md": storyMarkdown,
    "scene_plan.json": [],
    "shot_plan.json": [],
    "camera_plan.json": [],
    "image_prompts.json": [],
    "video_prompts.json": [],
    "voice_script.txt": "",
  };
}

describe("StoryTab", () => {
  it("shows an empty state when the production package doesn't exist yet", () => {
    render(<StoryTab productionPackage={null} />);

    expect(screen.getByText(/not generated yet/i)).toBeInTheDocument();
  });

  it("renders the story title as a heading", () => {
    const pkg = makePackage("# The Last Tree on Earth\n\n**Logline:** A test logline");

    render(<StoryTab productionPackage={pkg} />);

    expect(screen.getByRole("heading", { name: "The Last Tree on Earth" })).toBeInTheDocument();
  });

  it("renders bold text within a line without the raw ** markers", () => {
    const pkg = makePackage("**Logline:** A test logline");

    render(<StoryTab productionPackage={pkg} />);

    expect(screen.getByText("Logline:")).toBeInTheDocument();
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it("renders a scene subheading and a character list item", () => {
    const pkg = makePackage("## Characters\n\n- **Mira** (protagonist): brave\n\n### Scene 1: Opening");

    render(<StoryTab productionPackage={pkg} />);

    expect(screen.getByRole("heading", { name: "Characters" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Scene 1: Opening" })).toBeInTheDocument();
    expect(screen.getByText(/protagonist/)).toBeInTheDocument();
  });
});

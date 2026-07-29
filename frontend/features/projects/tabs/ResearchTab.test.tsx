import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProductionPackage } from "@/types/package";

import { ResearchTab } from "./ResearchTab";

function makePackage(researchBrief: ProductionPackage["research_brief.json"]): ProductionPackage {
  return {
    "manifest.json": { package_id: "p1", files: [] },
    "metadata.json": {
      package_id: "p1", source_plan_id: "", source_storyboard_id: "", generated_at: "",
      target_duration_seconds: 30, tone: null, audience: null, art_style: null,
    },
    "research_brief.json": researchBrief,
    "story.md": "",
    "scene_plan.json": [],
    "shot_plan.json": [],
    "camera_plan.json": [],
    "image_prompts.json": [],
    "video_prompts.json": [],
    "voice_script.txt": "",
  };
}

describe("ResearchTab", () => {
  it("shows an empty state when the production package doesn't exist yet", () => {
    render(<ResearchTab productionPackage={null} />);

    expect(screen.getByText(/not generated yet/i)).toBeInTheDocument();
  });

  it("shows a skipped message when research was skipped", () => {
    const pkg = makePackage({ status: "skipped", reason: "Research stage was skipped via --skip-research." });

    render(<ResearchTab productionPackage={pkg} />);

    expect(screen.getByText(/research was skipped/i)).toBeInTheDocument();
  });

  it("renders key facts and considerations when research was generated", () => {
    const pkg = makePackage({
      key_facts: ["Explorers often travel at dawn"],
      considerations: ["Keep the tone hopeful"],
      source_idea: "test idea",
      brief_id: "b1",
      generated_at: "2026-01-01T00:00:00Z",
    });

    render(<ResearchTab productionPackage={pkg} />);

    expect(screen.getByText("Explorers often travel at dawn")).toBeInTheDocument();
    expect(screen.getByText("Keep the tone hopeful")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProducerPackage } from "@/types/package";

import { TimelineTab } from "./TimelineTab";

describe("TimelineTab", () => {
  it("shows an empty state when the producer package doesn't exist yet", () => {
    render(<TimelineTab producerPackage={null} />);

    expect(screen.getByText(/not generated yet/i)).toBeInTheDocument();
  });

  it("shows an empty state when the package exists but has no timeline yet", () => {
    const pkg: ProducerPackage = { "manifest.json": { package_id: "p1", files: [] } };

    render(<TimelineTab producerPackage={pkg} />);

    expect(screen.getByText(/has not been generated/i)).toBeInTheDocument();
  });

  it("renders total duration, clips, and voice segments", () => {
    const pkg: ProducerPackage = {
      "manifest.json": { package_id: "p1", files: [] },
      "timeline_plan.json": {
        timeline_id: "t1",
        source_asset_manifest_id: "a1",
        clips: [
          { scene_id: 1, shot_id: 1, asset_type: "image", duration_seconds: 5, start_time: 0, end_time: 5 },
        ],
        voice_segments: [{ scene_id: 1, start_time: 0, end_time: 5 }],
        total_duration_seconds: 5,
        generated_at: "2026-01-01T00:00:00Z",
      },
    };

    render(<TimelineTab producerPackage={pkg} />);

    expect(screen.getByText("5s")).toBeInTheDocument();
    expect(screen.getByText("Scene 1, Shot 1")).toBeInTheDocument();
    expect(screen.getByText("image")).toBeInTheDocument();
  });

  it("never renders asset_path even though the real backend response includes it", () => {
    // TimelineClipEntry's TS type omits asset_path deliberately (see
    // types/package.ts), but the real wire payload from
    // GET .../producer-package still has it as an actual JS property -
    // simulate that here with a cast, since the component must not render
    // it regardless of what TypeScript does or doesn't know about.
    const rawPath = "D:\\ai_video_studio\\ai_video_studio\\outputs\\projects\\p1\\media\\images\\scene_1_shot_1.png";
    const pkg = {
      "manifest.json": { package_id: "p1", files: [] },
      "timeline_plan.json": {
        timeline_id: "t1",
        source_asset_manifest_id: "a1",
        clips: [
          {
            scene_id: 1, shot_id: 1, asset_path: rawPath, asset_type: "image",
            duration_seconds: 5, start_time: 0, end_time: 5,
          },
        ],
        voice_segments: [],
        total_duration_seconds: 5,
        generated_at: "2026-01-01T00:00:00Z",
      },
    } as unknown as ProducerPackage;

    const { container } = render(<TimelineTab producerPackage={pkg} />);

    expect(container.textContent).not.toContain(rawPath);
    expect(container.textContent).not.toContain("scene_1_shot_1.png");
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceTabs } from "./WorkspaceTabs";

describe("WorkspaceTabs", () => {
  it("renders all twelve workspace tabs", () => {
    render(<WorkspaceTabs active="Overview" onChange={vi.fn()} />);

    for (const tab of [
      "Overview", "Research", "Story", "Scene Plan", "Shot Plan", "Camera Plan",
      "Prompt Set", "Voice Script", "Timeline", "Media", "Render Preview", "Publishing",
    ]) {
      expect(screen.getByRole("tab", { name: tab })).toBeInTheDocument();
    }
  });

  it("marks the active tab as selected", () => {
    render(<WorkspaceTabs active="Timeline" onChange={vi.fn()} />);

    expect(screen.getByRole("tab", { name: "Timeline" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "false");
  });

  it("calls onChange with the clicked tab", () => {
    const onChange = vi.fn();
    render(<WorkspaceTabs active="Overview" onChange={onChange} />);

    fireEvent.click(screen.getByRole("tab", { name: "Render Preview" }));

    expect(onChange).toHaveBeenCalledWith("Render Preview");
  });
});

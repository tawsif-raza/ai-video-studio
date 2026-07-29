import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectStateBadge, RunStatusBadge } from "./StatusBadge";

describe("RunStatusBadge", () => {
  it("renders the status text", () => {
    render(<RunStatusBadge status="running" />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("renders the idle state distinctly from a real RunStatus", () => {
    render(<RunStatusBadge status="idle" />);
    expect(screen.getByText("idle")).toBeInTheDocument();
  });
});

describe("ProjectStateBadge", () => {
  it("renders underscores in ProjectState as spaces", () => {
    render(<ProjectStateBadge status="EDIT_PLAN_READY" />);
    expect(screen.getByText("EDIT PLAN READY")).toBeInTheDocument();
  });

  it("renders an early pipeline state as-is", () => {
    render(<ProjectStateBadge status="CREATED" />);
    expect(screen.getByText("CREATED")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RunLiveState } from "@/hooks/useRunEvents";

const { useRunEventsMock } = vi.hoisted(() => ({ useRunEventsMock: vi.fn() }));
vi.mock("@/hooks/useRunEvents", () => ({ useRunEvents: useRunEventsMock }));

import { LiveStatusPanel } from "./LiveStatusPanel";

function setLiveState(state: Partial<RunLiveState>) {
  useRunEventsMock.mockReturnValue({
    status: "idle",
    currentStage: null,
    progress: null,
    error: null,
    isConnected: false,
    ...state,
  });
}

describe("LiveStatusPanel", () => {
  beforeEach(() => {
    useRunEventsMock.mockReset();
  });

  it("displays current stage, status, and progress while running", () => {
    setLiveState({ status: "running", currentStage: "running", progress: 50, isConnected: true });

    render(<LiveStatusPanel runId="run-1" stageLabel="Producer Studio" />);

    expect(screen.getAllByText("running")).toHaveLength(2); // status badge + current-stage field
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("shows a success message and calls onTerminal when the run succeeds", () => {
    setLiveState({ status: "succeeded", progress: 100 });
    const onTerminal = vi.fn();

    render(<LiveStatusPanel runId="run-1" stageLabel="Execution Engine" onTerminal={onTerminal} />);

    expect(screen.getByText("Completed successfully.")).toBeInTheDocument();
    expect(onTerminal).toHaveBeenCalledTimes(1);
  });

  it("shows the error message and calls onTerminal when the run fails", () => {
    setLiveState({ status: "failed", error: "ffmpeg not found" });
    const onTerminal = vi.fn();

    render(<LiveStatusPanel runId="run-1" stageLabel="Execution Engine" onTerminal={onTerminal} />);

    expect(screen.getByText("ffmpeg not found")).toBeInTheDocument();
    expect(onTerminal).toHaveBeenCalledTimes(1);
  });

  it("does not call onTerminal while still queued or running", () => {
    setLiveState({ status: "running" });
    const onTerminal = vi.fn();

    render(<LiveStatusPanel runId="run-1" stageLabel="Producer Studio" onTerminal={onTerminal} />);

    expect(onTerminal).not.toHaveBeenCalled();
  });
});

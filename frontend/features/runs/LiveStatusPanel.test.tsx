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

  it("shows a render whose ffmpeg step failed as failed, not succeeded (issue #2)", () => {
    setLiveState({
      status: "succeeded",
      progress: 100,
      result: { render: { success: false, error: "ffmpeg exited with code 1" } },
    });

    render(<LiveStatusPanel runId="run-1" stageLabel="Render" />);

    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.queryByText("succeeded")).not.toBeInTheDocument();
    expect(screen.queryByText("Completed successfully.")).not.toBeInTheDocument();
    expect(screen.getByText(/ffmpeg exited with code 1/)).toBeInTheDocument();
  });

  it("shows a render that failed postflight validation as failed, naming the check", () => {
    setLiveState({
      status: "succeeded",
      progress: 100,
      result: {
        render: { success: true },
        validation: {
          is_valid: false,
          checks: [
            { name: "video_stream", passed: true },
            { name: "resolution", passed: false },
          ],
        },
      },
    });

    render(<LiveStatusPanel runId="run-1" stageLabel="Render" />);

    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText(/failed postflight validation: resolution$/)).toBeInTheDocument();
  });

  it("still reports a passing render as completed successfully", () => {
    setLiveState({
      status: "succeeded",
      progress: 100,
      result: { render: { success: true }, validation: { is_valid: true, checks: [] } },
    });

    render(<LiveStatusPanel runId="run-1" stageLabel="Render" />);

    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(screen.getByText("Completed successfully.")).toBeInTheDocument();
  });
});

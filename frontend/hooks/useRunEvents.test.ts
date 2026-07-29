import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useRunEvents } from "./useRunEvents";

/** Minimal, controllable stand-in for the browser's EventSource - jsdom
 * doesn't implement it, and this lets tests deterministically emit the
 * exact named events web_api/sse.py's _events_for() sends (W6). */
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  private listeners: Record<string, ((event: MessageEvent) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(handler);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners[type] ?? []) {
      handler(new MessageEvent(type, { data: JSON.stringify(data) }));
    }
  }
}

describe("useRunEvents", () => {
  let OriginalEventSource: typeof EventSource | undefined;

  beforeEach(() => {
    OriginalEventSource = global.EventSource;
    FakeEventSource.instances = [];
    // @ts-expect-error - test double, not the real browser EventSource
    global.EventSource = FakeEventSource;
  });

  afterEach(() => {
    global.EventSource = OriginalEventSource as typeof EventSource;
  });

  it("stays idle and opens no connection when runId is null", () => {
    const { result } = renderHook(() => useRunEvents(null));

    expect(result.current.status).toBe("idle");
    expect(result.current.isConnected).toBe(false);
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("connects to GET /runs/{runId}/events", () => {
    renderHook(() => useRunEvents("run-1"));

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe("http://127.0.0.1:8000/runs/run-1/events");
  });

  it("marks connected once the stream actually opens", () => {
    const { result } = renderHook(() => useRunEvents("run-1"));
    const source = FakeEventSource.instances[0];

    act(() => source.emit("open", {}));

    expect(result.current.isConnected).toBe(true);
  });

  it("processes run_started -> stage_changed -> progress -> completed in order", () => {
    const { result } = renderHook(() => useRunEvents("run-1"));
    const source = FakeEventSource.instances[0];

    act(() => source.emit("open", {}));
    act(() =>
      source.emit("run_started", {
        run_id: "run-1",
        project_id: "p1",
        type: "producer",
        status: "running",
      }),
    );
    expect(result.current.status).toBe("running");

    act(() => source.emit("stage_changed", { current_stage: "running" }));
    expect(result.current.currentStage).toBe("running");

    act(() => source.emit("progress", { progress: 50 }));
    expect(result.current.progress).toBe(50);

    act(() => source.emit("progress", { progress: 100 }));
    act(() => source.emit("completed", { status: "succeeded" }));

    expect(result.current.status).toBe("succeeded");
    expect(result.current.progress).toBe(100);
    expect(result.current.isConnected).toBe(false);
  });

  it("closes the connection once a completed event arrives", () => {
    renderHook(() => useRunEvents("run-1"));
    const source = FakeEventSource.instances[0];

    act(() => source.emit("completed", { status: "succeeded" }));

    expect(source.closed).toBe(true);
  });

  it("processes a failed event with its error message and closes the connection", () => {
    const { result } = renderHook(() => useRunEvents("run-1"));
    const source = FakeEventSource.instances[0];

    act(() => source.emit("failed", { status: "failed", error: "ffmpeg not found" }));

    expect(result.current.status).toBe("failed");
    expect(result.current.error).toBe("ffmpeg not found");
    expect(source.closed).toBe(true);
  });

  it("closes the EventSource on unmount, independent of run outcome", () => {
    const { unmount } = renderHook(() => useRunEvents("run-1"));
    const source = FakeEventSource.instances[0];

    unmount();

    expect(source.closed).toBe(true);
  });

  it("opens a new connection and resets state when runId changes", () => {
    const { result, rerender } = renderHook(({ runId }) => useRunEvents(runId), {
      initialProps: { runId: "run-1" },
    });
    const firstSource = FakeEventSource.instances[0];
    act(() => firstSource.emit("failed", { status: "failed", error: "boom" }));
    expect(result.current.status).toBe("failed");

    rerender({ runId: "run-2" });

    expect(firstSource.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[1].url).toBe("http://127.0.0.1:8000/runs/run-2/events");

    act(() => FakeEventSource.instances[1].emit("open", {}));
    expect(result.current.status).toBe("idle");
    expect(result.current.error).toBeNull();
  });
});

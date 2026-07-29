"use client";

import { useEffect, useState } from "react";

import { runEventsUrl } from "@/api/sse";
import type {
  CompletedEvent,
  FailedEvent,
  ProgressEvent,
  RunStartedEvent,
  RunStatus,
  StageChangedEvent,
} from "@/types/run";

export interface RunLiveState {
  status: RunStatus | "idle";
  currentStage: string | null;
  progress: number | null;
  error: string | null;
  isConnected: boolean;
}

const initialState: RunLiveState = {
  status: "idle",
  currentStage: null,
  progress: null,
  error: null,
  isConnected: false,
};

/**
 * Subscribes to GET /runs/{runId}/events (Milestone W6) via the browser's
 * native EventSource - no polling, no WebSockets. Pass null/undefined to
 * stay disconnected (e.g. before any run has been triggered yet).
 *
 * Closes the connection itself once a terminal event (completed/failed)
 * arrives, mirroring the backend's own "completed runs auto-close the
 * stream" behavior, and also on unmount or when runId changes.
 */
export function useRunEvents(runId: string | null | undefined): RunLiveState {
  const [state, setState] = useState<RunLiveState>(initialState);

  useEffect(() => {
    // No setState call for the "no run to subscribe to" case - the hook
    // returns initialState directly below when runId is falsy, so there's
    // nothing to reset here.
    if (!runId) return;

    const source = new EventSource(runEventsUrl(runId));

    // Reset to a fresh initial state only once the connection genuinely
    // opens (a real browser callback, not a synchronous assumption) -
    // this is also where a runId change's stale state from the previous
    // subscription gets cleared.
    const onOpen = () => {
      setState({ ...initialState, isConnected: true });
    };
    const onRunStarted = (event: MessageEvent<string>) => {
      const data = JSON.parse(event.data) as RunStartedEvent;
      setState((prev) => ({ ...prev, status: data.status }));
    };
    const onStageChanged = (event: MessageEvent<string>) => {
      const data = JSON.parse(event.data) as StageChangedEvent;
      setState((prev) => ({ ...prev, currentStage: data.current_stage }));
    };
    const onProgress = (event: MessageEvent<string>) => {
      const data = JSON.parse(event.data) as ProgressEvent;
      setState((prev) => ({ ...prev, progress: data.progress }));
    };
    const onCompleted = (event: MessageEvent<string>) => {
      const data = JSON.parse(event.data) as CompletedEvent;
      setState((prev) => ({ ...prev, status: data.status, isConnected: false }));
      source.close();
    };
    const onFailed = (event: MessageEvent<string>) => {
      const data = JSON.parse(event.data) as FailedEvent;
      setState((prev) => ({ ...prev, status: data.status, error: data.error, isConnected: false }));
      source.close();
    };
    const onError = () => {
      // A transport-level hiccup (e.g. the dev server restarting) -
      // EventSource retries connections on its own; just reflect that
      // we're momentarily not connected rather than treating it as a
      // run failure.
      setState((prev) => ({ ...prev, isConnected: false }));
    };

    source.addEventListener("open", onOpen);
    source.addEventListener("run_started", onRunStarted);
    source.addEventListener("stage_changed", onStageChanged);
    source.addEventListener("progress", onProgress);
    source.addEventListener("completed", onCompleted);
    source.addEventListener("failed", onFailed);
    source.addEventListener("error", onError);

    return () => {
      source.close();
    };
  }, [runId]);

  if (!runId) return initialState;
  return state;
}

"use client";

import { useEffect, useState } from "react";

import { getRun } from "@/api/runs";
import type { Run } from "@/types/run";

interface UseRunResult {
  run: Run | null;
  isLoading: boolean;
  error: string | null;
}

/** One-shot fetch of GET /runs/{id} (W2) by run_id - used where a run's
 * full result (readiness/credentials/authentication for a publish run,
 * etc.) is needed after the fact, distinct from useRunEvents' live SSE
 * subscription which stops once a run reaches a terminal state. Pass
 * null/undefined to skip fetching (e.g. no run has been triggered yet). */
export function useRun(runId: string | null | undefined): UseRunResult {
  const [run, setRun] = useState<Run | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(runId));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) {
      return;
    }
    let cancelled = false;

    getRun(runId)
      .then((result) => {
        if (cancelled) return;
        setRun(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load run");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (!runId) {
    return { run: null, isLoading: false, error: null };
  }
  return { run, isLoading, error };
}

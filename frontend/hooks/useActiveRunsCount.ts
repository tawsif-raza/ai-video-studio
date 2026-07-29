"use client";

import { useEffect, useState } from "react";

import { getPublishStatus, getRenderStatus } from "@/api/runs";
import { ApiError } from "@/api/client";
import type { Project } from "@/types/project";

interface UseActiveRunsCountResult {
  count: number | null;
  isLoading: boolean;
}

/**
 * Best-effort "how many runs are active right now" tile, built entirely
 * from existing endpoints (GET /projects/{id}/render/status,
 * .../publish/status - W4/W5) - there is no aggregate "list all runs"
 * endpoint (director/producer never got a GET .../status sibling the way
 * render/publish did), so this necessarily undercounts director/producer
 * runs. Labeled honestly in the UI rather than presented as a complete
 * count; a real fix belongs in a future milestone that adds a proper
 * cross-project run-listing endpoint.
 */
export function useActiveRunsCount(projects: Project[]): UseActiveRunsCountResult {
  const [count, setCount] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // The "nothing to check" case is handled outside the effect (see the
    // early return of this hook, below) - no setState call belongs here
    // for it.
    if (projects.length === 0) return;

    let cancelled = false;

    const checks = projects.flatMap((project) => [
      getRenderStatus(project.project_id).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }),
      getPublishStatus(project.project_id).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }),
    ]);

    Promise.all(checks)
      .then((results) => {
        if (cancelled) return;
        const active = results.filter(
          (status) => status !== null && (status.status === "queued" || status.status === "running")
        ).length;
        setCount(active);
      })
      .catch(() => {
        if (!cancelled) setCount(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projects]);

  if (projects.length === 0) {
    return { count: 0, isLoading: false };
  }
  return { count, isLoading };
}

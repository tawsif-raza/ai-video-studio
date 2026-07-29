"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { getPublishStatus, getRenderStatus } from "@/api/runs";
import type { PublishStageStatus, StageStatus } from "@/types/run";

interface StageSnapshots {
  render: StageStatus | null;
  publish: PublishStageStatus | null;
  isLoading: boolean;
}

/**
 * Best-effort "last known render/publish run" snapshot for a project,
 * fetched once via the existing GET .../render/status and .../publish/status
 * endpoints (W4/W5) - a fallback for Active Runs when nothing has been
 * triggered in the current browser session (e.g. after a page refresh).
 * Director/Producer have no equivalent status endpoint, so they're not
 * represented here; only a live, session-tracked run (via useRunEvents)
 * can show those.
 */
export function useStageSnapshots(projectId: string): StageSnapshots {
  const [render, setRender] = useState<StageStatus | null>(null);
  const [publish, setPublish] = useState<PublishStageStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const ignore404 = (err: unknown) => {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    };

    Promise.all([
      getRenderStatus(projectId).catch(ignore404),
      getPublishStatus(projectId).catch(ignore404),
    ])
      .then(([renderStatus, publishStatus]) => {
        if (cancelled) return;
        setRender(renderStatus);
        setPublish(publishStatus);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return { render, publish, isLoading };
}

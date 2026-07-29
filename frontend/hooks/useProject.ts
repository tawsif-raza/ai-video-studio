"use client";

import { useCallback, useEffect, useState } from "react";

import { getProject } from "@/api/projects";
import type { Project } from "@/types/project";

interface UseProjectResult {
  project: Project | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Thin data-fetching hook over GET /projects/{id} (W1). */
export function useProject(projectId: string): UseProjectResult {
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    getProject(projectId)
      .then((result) => {
        if (cancelled) return;
        setProject(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load project");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, refetchToken]);

  const refetch = useCallback(() => setRefetchToken((t) => t + 1), []);

  return { project, isLoading, error, refetch };
}

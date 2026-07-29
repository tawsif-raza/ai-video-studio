"use client";

import { useCallback, useEffect, useState } from "react";

import { listProjects } from "@/api/projects";
import type { Project } from "@/types/project";

interface UseProjectsResult {
  projects: Project[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Thin data-fetching hook over GET /projects (W1) - list_projects()
 * already returns newest-first, so no client-side sorting is needed here. */
export function useProjects(): UseProjectsResult {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    // No setState call before this - isLoading/error are left at whatever
    // they were (true/null on first mount; the previous result while a
    // refetch is in flight) until the fetch actually settles below.
    listProjects()
      .then((result) => {
        if (cancelled) return;
        setProjects(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load projects");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [refetchToken]);

  const refetch = useCallback(() => setRefetchToken((t) => t + 1), []);

  return { projects, isLoading, error, refetch };
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { getProductionPackage } from "@/api/packages";
import type { ProductionPackage } from "@/types/package";

interface UseProductionPackageResult {
  productionPackage: ProductionPackage | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Fetches GET /projects/{id}/production-package (W7.5). A 404 means
 * "not generated yet" - a normal, expected state for a project still early
 * in its lifecycle, not an error to surface - so it resolves to
 * productionPackage: null rather than populating `error`. Any other
 * failure is a real error. Exposes `refetch` so callers can force a
 * re-fetch once a Director Studio run completes in the same page session
 * (e.g. via SSE) - without it, a 404 fetched before the run finished would
 * never be replaced until a full page reload remounted this hook. */
export function useProductionPackage(projectId: string): UseProductionPackageResult {
  const [productionPackage, setProductionPackage] = useState<ProductionPackage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    getProductionPackage(projectId)
      .then((result) => {
        if (cancelled) return;
        setProductionPackage(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setProductionPackage(null);
        } else {
          setError(err instanceof Error ? err.message : "Failed to load production package");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, refetchToken]);

  const refetch = useCallback(() => setRefetchToken((t) => t + 1), []);

  return { productionPackage, isLoading, error, refetch };
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { getProducerPackage } from "@/api/packages";
import type { ProducerPackage } from "@/types/package";

interface UseProducerPackageResult {
  producerPackage: ProducerPackage | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

/** Same convention as useProductionPackage - a 404 (Producer Package not
 * generated yet) resolves to producerPackage: null, not an error. Exposes
 * `refetch` so callers can force a re-fetch once a Producer Studio run
 * completes in the same page session. */
export function useProducerPackage(projectId: string): UseProducerPackageResult {
  const [producerPackage, setProducerPackage] = useState<ProducerPackage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refetchToken, setRefetchToken] = useState(0);

  useEffect(() => {
    let cancelled = false;

    getProducerPackage(projectId)
      .then((result) => {
        if (cancelled) return;
        setProducerPackage(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setProducerPackage(null);
        } else {
          setError(err instanceof Error ? err.message : "Failed to load producer package");
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

  return { producerPackage, isLoading, error, refetch };
}

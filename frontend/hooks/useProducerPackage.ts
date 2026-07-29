"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/api/client";
import { getProducerPackage } from "@/api/packages";
import type { ProducerPackage } from "@/types/package";

interface UseProducerPackageResult {
  producerPackage: ProducerPackage | null;
  isLoading: boolean;
  error: string | null;
}

/** Same convention as useProductionPackage - a 404 (Producer Package not
 * generated yet) resolves to producerPackage: null, not an error. */
export function useProducerPackage(projectId: string): UseProducerPackageResult {
  const [producerPackage, setProducerPackage] = useState<ProducerPackage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  }, [projectId]);

  return { producerPackage, isLoading, error };
}

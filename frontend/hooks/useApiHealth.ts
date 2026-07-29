"use client";

import { useEffect, useState } from "react";

import { apiGet } from "@/api/client";

export type ApiHealthState = "checking" | "online" | "offline";

/**
 * Backend connectivity check for the layout's persistent status indicator
 * (GET /health, W1). Distinct from Milestone W6's "no polling" rule, which
 * is specifically about run-progress updates (SSE replaces polling there);
 * a coarse, infrequent liveness ping for a status dot is a different,
 * ordinary use of an interval and isn't what that constraint is about.
 */
export function useApiHealth(intervalMs = 30_000): ApiHealthState {
  const [state, setState] = useState<ApiHealthState>("checking");

  useEffect(() => {
    let cancelled = false;

    const check = () => {
      apiGet<{ status: string }>("/health")
        .then(() => {
          if (!cancelled) setState("online");
        })
        .catch(() => {
          if (!cancelled) setState("offline");
        });
    };

    check();
    const id = setInterval(check, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}

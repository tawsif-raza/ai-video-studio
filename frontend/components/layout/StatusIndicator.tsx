"use client";

import { useApiHealth } from "@/hooks/useApiHealth";

const LABEL: Record<string, string> = {
  checking: "Checking backend…",
  online: "Backend connected",
  offline: "Backend unreachable",
};

const DOT_CLASSES: Record<string, string> = {
  checking: "bg-amber-400",
  online: "bg-emerald-500",
  offline: "bg-red-500",
};

export function StatusIndicator() {
  const health = useApiHealth();

  return (
    <div
      className="flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400"
      title={LABEL[health]}
    >
      <span className={`h-2 w-2 rounded-full ${DOT_CLASSES[health]}`} aria-hidden="true" />
      {LABEL[health]}
    </div>
  );
}

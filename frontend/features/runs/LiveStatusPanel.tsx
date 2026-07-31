"use client";

import { useEffect, useRef } from "react";

import { RunStatusBadge } from "@/components/ui/StatusBadge";
import { Card, CardTitle } from "@/components/ui/Card";
import { useRunEvents } from "@/hooks/useRunEvents";

/**
 * Producer Studio's run result carries asset_validation.missing_shot_count
 * (web_api/producer_runner.py) - a plain number the backend already computed
 * rather than something parsed out of issue text. A run can show "Completed
 * successfully" while some shots were tolerated as missing (rendered as
 * black placeholders) - this makes that visible instead of silent.
 */
function MissingShotNotice({ result }: { result: Record<string, unknown> | null }) {
  const assetValidation = result?.asset_validation;
  if (!assetValidation || typeof assetValidation !== "object") return null;

  const missingShotCount = (assetValidation as Record<string, unknown>).missing_shot_count;
  if (typeof missingShotCount !== "number" || missingShotCount <= 0) return null;

  return (
    <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
      {missingShotCount} shot{missingShotCount === 1 ? "" : "s"} {missingShotCount === 1 ? "is" : "are"} missing an
      image or video - rendered as a plain black frame for now. Check the Media tab and upload the missing file(s)
      if you want real visuals there.
    </p>
  );
}

/**
 * Live view of one run, driven entirely by GET /runs/{runId}/events (W6)
 * via the browser's native EventSource - no polling, no WebSockets.
 * Displays exactly the four things Milestone W7 asks for: current stage,
 * current status, progress, and completion/failure.
 */
export function LiveStatusPanel({
  runId,
  stageLabel,
  onTerminal,
}: {
  runId: string;
  stageLabel: string;
  onTerminal?: () => void;
}) {
  const live = useRunEvents(runId);
  const firedRef = useRef(false);

  useEffect(() => {
    firedRef.current = false;
  }, [runId]);

  useEffect(() => {
    if (!firedRef.current && (live.status === "succeeded" || live.status === "failed")) {
      firedRef.current = true;
      onTerminal?.();
    }
  }, [live.status, onTerminal]);

  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Live Status - {stageLabel}</CardTitle>
        <RunStatusBadge status={live.status} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Current stage</dt>
          <dd className="mt-0.5 text-zinc-900 dark:text-zinc-50">{live.currentStage ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Progress</dt>
          <dd className="mt-0.5 text-zinc-900 dark:text-zinc-50">
            {live.progress === null ? "—" : `${live.progress}%`}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Connection</dt>
          <dd className="mt-0.5 text-zinc-900 dark:text-zinc-50">
            {live.isConnected ? "Live" : "Closed"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Run ID</dt>
          <dd className="mt-0.5 truncate font-mono text-xs text-zinc-500 dark:text-zinc-400">{runId}</dd>
        </div>
      </dl>

      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div
          className={`h-full rounded-full transition-all ${
            live.status === "failed" ? "bg-red-500" : "bg-indigo-600"
          }`}
          style={{ width: `${live.progress ?? 0}%` }}
        />
      </div>

      {live.status === "failed" && live.error && (
        <p className="mt-3 rounded-lg border border-red-200 bg-red-50 p-2.5 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {live.error}
        </p>
      )}
      {live.status === "succeeded" && (
        <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
          Completed successfully.
        </p>
      )}
      {live.status === "succeeded" && <MissingShotNotice result={live.result} />}
    </Card>
  );
}

"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { RunStatusBadge } from "@/components/ui/StatusBadge";
import { LiveStatusPanel } from "@/features/runs/LiveStatusPanel";
import type { PublishStageStatus, RunAccepted, StageStatus } from "@/types/run";

/**
 * Shows the live, SSE-driven run this browser session just triggered
 * (activeRun, if set) - or, when there isn't one (e.g. after a page
 * refresh), the last known render/publish status passed in from the
 * parent (fetched once via REST, W4/W5, and shared with RecentActivity
 * rather than fetched twice). There's no backend endpoint for "list every
 * run for this project," so this is the most complete honest picture
 * available from existing endpoints alone.
 */
export function ActiveRuns({
  activeRun,
  render,
  publish,
  isLoadingSnapshots,
  onRunTerminal,
}: {
  activeRun: { run: RunAccepted; stageLabel: string } | null;
  render: StageStatus | null;
  publish: PublishStageStatus | null;
  isLoadingSnapshots: boolean;
  onRunTerminal?: () => void;
}) {
  if (activeRun) {
    return (
      <LiveStatusPanel
        runId={activeRun.run.run_id}
        stageLabel={activeRun.stageLabel}
        onTerminal={onRunTerminal}
      />
    );
  }

  const snapshots = [
    render && { label: "Execution Engine (render)", status: render },
    publish && { label: "Publishing Engine", status: publish },
  ].filter((s): s is { label: string; status: StageStatus } => Boolean(s));

  return (
    <Card>
      <CardTitle>Active Runs</CardTitle>
      {isLoadingSnapshots && <p className="mt-2 text-sm text-zinc-400">Checking for runs…</p>}
      {!isLoadingSnapshots && snapshots.length === 0 && (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          No run triggered in this session yet, and no prior render/publish run found.
        </p>
      )}
      {snapshots.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {snapshots.map((s) => (
            <li key={s.label} className="flex items-center justify-between text-sm">
              <span className="text-zinc-700 dark:text-zinc-300">{s.label}</span>
              <RunStatusBadge status={s.status.status} />
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-zinc-400 dark:text-zinc-500">
        Showing the last known run for stages that expose a status endpoint. Director/Producer runs are only
        visible here while this browser tab has them open live.
      </p>
    </Card>
  );
}

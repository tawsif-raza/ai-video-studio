"use client";

import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { RunStatusBadge } from "@/components/ui/StatusBadge";
import { useRun } from "@/hooks/useRun";
import type { ProducerPackage } from "@/types/package";
import type { PublishStageStatus } from "@/types/run";

interface ActiveRun {
  runId: string;
  stageLabel: string;
}

/**
 * "Last upload result" is deliberately not a real upload outcome - no
 * backend endpoint for that exists (PublishingEngineController.run() never
 * uploads; WEB_DASHBOARD_ARCHITECTURE.md SS12 keeps that out of scope, see
 * the W5 report). What this shows instead, honestly, is the readiness/
 * credentials/authentication result of the last publish run *this browser
 * session* triggered (via GET /runs/{id}, W2) - the closest real thing to
 * "did the last publish attempt look ready to go."
 */
export function PublishingTab({
  producerPackage,
  publishStatus,
  activeRun,
}: {
  producerPackage: ProducerPackage | null;
  publishStatus: PublishStageStatus | null;
  activeRun: ActiveRun | null;
}) {
  const isPublishRun = activeRun?.stageLabel === "Publishing Engine";
  const { run } = useRun(isPublishRun ? activeRun!.runId : null);

  if (!producerPackage) {
    return <EmptyState message="Producer package not generated yet - run Producer Studio first." />;
  }

  const metadata = producerPackage["publishing_metadata.json"];

  return (
    <div className="flex flex-col gap-4">
      {metadata ? (
        <Card>
          <CardTitle>Publishing Metadata</CardTitle>
          <dl className="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Title</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{metadata.canonical.title}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Category</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{metadata.canonical.category}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Description</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{metadata.canonical.description}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Keywords</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{metadata.canonical.keywords.join(", ") || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">YouTube Visibility</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{metadata.youtube.visibility}</dd>
            </div>
          </dl>
        </Card>
      ) : (
        <EmptyState message="Publishing metadata has not been generated for this project yet." />
      )}

      <Card>
        <CardTitle>Current Publishing Status</CardTitle>
        {publishStatus ? (
          <div className="mt-2 flex items-center gap-3 text-sm">
            <RunStatusBadge status={publishStatus.status} />
            <span className="text-zinc-500 dark:text-zinc-400">
              Project state: {publishStatus.project_state}
            </span>
          </div>
        ) : (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No publish run found for this project.</p>
        )}
      </Card>

      <Card>
        <CardTitle>Last Upload Result</CardTitle>
        {!isPublishRun && (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            No publish run triggered in this session yet.
          </p>
        )}
        {isPublishRun && !run?.result && (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">Waiting for the publish run to finish…</p>
        )}
        {isPublishRun && run?.result && (
          <div className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
            <p>
              Ready to publish:{" "}
              <span className="font-medium">{String(run.result.ready_to_publish)}</span>
            </p>
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
              No real upload happens yet - this system stops at readiness checking (credentials, authentication,
              metadata). See the full result via the run detail API for complete readiness/credential/
              authentication checks.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}

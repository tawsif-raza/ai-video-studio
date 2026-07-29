"use client";

import { useState } from "react";

import { ApiError } from "@/api/client";
import { runProducer, runPublish, runRender } from "@/api/runs";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import type { RunAccepted } from "@/types/run";

type StageKey = "producer" | "render" | "publish";

/**
 * "Run Director" is intentionally rendered disabled, not omitted: this
 * milestone's own spec asks for all four buttons, but there is no backend
 * endpoint to re-run Director Studio on an *existing* project_id -
 * POST /projects (W2) always creates a brand-new project. Rather than
 * silently dropping the button or pretending it works, it's shown with an
 * explanation and routes the user to the one place Director Studio really
 * is available (Quick Actions -> New Project on the dashboard/projects
 * page). Producer/Render/Publish each invoke their real backend endpoint
 * with no client-side eligibility gating beyond "is another run already
 * active" - the backend is the single source of truth for whether a
 * project is ready (400) or busy (409); this component just surfaces
 * whatever it says.
 */
export function RunControls({
  projectId,
  onRunStarted,
}: {
  projectId: string;
  onRunStarted: (run: RunAccepted, stageLabel: string) => void;
}) {
  const [loadingStage, setLoadingStage] = useState<StageKey | null>(null);
  const [errors, setErrors] = useState<Partial<Record<StageKey, string>>>({});

  const trigger = async (stage: StageKey, label: string, action: () => Promise<RunAccepted>) => {
    setLoadingStage(stage);
    setErrors((prev) => ({ ...prev, [stage]: undefined }));
    try {
      const result = await action();
      onRunStarted(result, label);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Request failed";
      setErrors((prev) => ({ ...prev, [stage]: message }));
    } finally {
      setLoadingStage(null);
    }
  };

  return (
    <Card>
      <CardTitle>Run Controls</CardTitle>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          disabled
          title="Director Studio only runs when creating a new project - use Quick Actions -> New Project"
        >
          Run Director
        </Button>
        <Button
          variant="secondary"
          isLoading={loadingStage === "producer"}
          onClick={() => trigger("producer", "Producer Studio", () => runProducer(projectId))}
        >
          Run Producer
        </Button>
        <Button
          variant="secondary"
          isLoading={loadingStage === "render"}
          onClick={() => trigger("render", "Execution Engine", () => runRender(projectId))}
        >
          Render
        </Button>
        <Button
          variant="secondary"
          isLoading={loadingStage === "publish"}
          onClick={() => trigger("publish", "Publishing Engine", () => runPublish(projectId))}
        >
          Publish
        </Button>
      </div>
      <p className="mt-3 text-xs text-zinc-400 dark:text-zinc-500">
        &ldquo;Run Director&rdquo; is disabled here: POST /projects always creates a new project, so re-running
        Director Studio on an existing one isn&rsquo;t something the backend supports. Start a new run from the
        Projects page instead.
      </p>
      {Object.entries(errors).map(([stage, message]) =>
        message ? (
          <p key={stage} className="mt-2 text-sm text-red-600 dark:text-red-400">
            {message}
          </p>
        ) : null,
      )}
    </Card>
  );
}

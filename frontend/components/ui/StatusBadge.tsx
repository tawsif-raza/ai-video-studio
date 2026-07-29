import type { ProjectState } from "@/types/project";
import type { RunStatus } from "@/types/run";

const RUN_STATUS_CLASSES: Record<RunStatus | "idle", string> = {
  idle: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  queued: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  succeeded: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
};

export function RunStatusBadge({ status }: { status: RunStatus | "idle" }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${RUN_STATUS_CLASSES[status]}`}
    >
      {status}
    </span>
  );
}

/** Terminal/late-stage states read as "done" (emerald); early states read
 * as "in progress" (blue) - a coarse, presentational grouping only, not a
 * reimplementation of the state machine's actual transition rules. */
const LATE_PROJECT_STATES: ProjectState[] = ["EDIT_PLAN_READY", "VIDEO_RENDERED"];

export function ProjectStateBadge({ status }: { status: ProjectState }) {
  const isLate = LATE_PROJECT_STATES.includes(status);
  const classes = isLate
    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
    : "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300";

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${classes}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

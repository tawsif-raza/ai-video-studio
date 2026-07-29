import { Card, CardTitle } from "@/components/ui/Card";
import type { PublishStageStatus, StageStatus } from "@/types/run";
import type { Project } from "@/types/project";

interface ActivityEntry {
  label: string;
  timestamp: string;
}

/**
 * There is no activity-log endpoint - this synthesizes a small,
 * chronologically-sorted list purely from timestamps already present in
 * data this page already fetched (project.created_at, and the render/
 * publish status snapshots), rather than fabricating an audit trail the
 * backend doesn't provide.
 */
export function RecentActivity({
  project,
  render,
  publish,
}: {
  project: Project;
  render: StageStatus | null;
  publish: PublishStageStatus | null;
}) {
  const entries: ActivityEntry[] = [{ label: "Project created", timestamp: project.created_at }];

  if (render) {
    entries.push({
      label: `Render ${render.status} (${render.current_stage})`,
      timestamp: render.updated_at,
    });
  }
  if (publish) {
    entries.push({
      label: `Publish ${publish.status} (${publish.current_stage})`,
      timestamp: publish.updated_at,
    });
  }

  entries.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return (
    <Card>
      <CardTitle>Recent Activity</CardTitle>
      <ul className="mt-3 flex flex-col gap-2">
        {entries.map((entry) => (
          <li key={`${entry.label}-${entry.timestamp}`} className="flex items-center justify-between text-sm">
            <span className="text-zinc-700 dark:text-zinc-300">{entry.label}</span>
            <span className="text-xs text-zinc-400 dark:text-zinc-500">
              {new Date(entry.timestamp).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

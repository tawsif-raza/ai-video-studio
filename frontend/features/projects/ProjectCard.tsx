import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { ProjectStateBadge } from "@/components/ui/StatusBadge";
import type { Project } from "@/types/project";

/**
 * The backend's Project model (project_manager/project.py) has no "name"
 * field and no separate "updated_at" timestamp - only project_id, status,
 * and created_at. This card shows project_id as the identifier (labeled
 * honestly, not invented as a "name") and created_at labeled "Created"
 * rather than claiming "Last updated," which would overstate what the
 * data actually is. See the W7 report for the full rationale.
 */
export function ProjectCard({ project }: { project: Project }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <p className="truncate font-mono text-sm font-medium text-zinc-900 dark:text-zinc-50">
          {project.project_id}
        </p>
        <ProjectStateBadge status={project.status} />
      </div>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Created {new Date(project.created_at).toLocaleString()}
      </p>
      <Link
        href={`/projects/${project.project_id}`}
        className="mt-1 inline-flex items-center justify-center rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-medium text-zinc-900 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700"
      >
        Open
      </Link>
    </Card>
  );
}

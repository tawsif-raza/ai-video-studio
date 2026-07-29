import { Card, CardTitle } from "@/components/ui/Card";
import { ProjectStateBadge } from "@/components/ui/StatusBadge";
import type { Project } from "@/types/project";

export function Overview({ project }: { project: Project }) {
  return (
    <Card>
      <CardTitle>Overview</CardTitle>
      <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Project ID</dt>
          <dd className="mt-0.5 break-all font-mono text-sm text-zinc-900 dark:text-zinc-50">
            {project.project_id}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Status</dt>
          <dd className="mt-0.5">
            <ProjectStateBadge status={project.status} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-zinc-400 dark:text-zinc-500">Created</dt>
          <dd className="mt-0.5 text-sm text-zinc-900 dark:text-zinc-50">
            {new Date(project.created_at).toLocaleString()}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

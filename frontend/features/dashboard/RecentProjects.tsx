import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/Card";
import { ProjectStateBadge } from "@/components/ui/StatusBadge";
import type { Project } from "@/types/project";

export function RecentProjects({ projects }: { projects: Project[] }) {
  const recent = projects.slice(0, 5);

  return (
    <Card>
      <CardTitle>Recently Updated Projects</CardTitle>
      {recent.length === 0 ? (
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">No projects yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
          {recent.map((project) => (
            <li key={project.project_id} className="flex items-center justify-between py-2.5">
              <div className="min-w-0">
                <Link
                  href={`/projects/${project.project_id}`}
                  className="truncate font-mono text-sm text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  {project.project_id}
                </Link>
                <p className="text-xs text-zinc-400 dark:text-zinc-500">
                  {new Date(project.created_at).toLocaleString()}
                </p>
              </div>
              <ProjectStateBadge status={project.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

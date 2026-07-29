import { Suspense } from "react";

import { PageShell } from "@/components/layout/PageShell";
import { ProjectWorkspace } from "@/features/projects/ProjectWorkspace";

export default async function ProjectWorkspacePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;

  return (
    <PageShell title="Project Workspace" subtitle={projectId}>
      <Suspense fallback={<p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}>
        <ProjectWorkspace projectId={projectId} />
      </Suspense>
    </PageShell>
  );
}

import { Suspense } from "react";

import { PageShell } from "@/components/layout/PageShell";
import { ProjectList } from "@/features/projects/ProjectList";

export default function ProjectsPage() {
  return (
    <PageShell title="Projects" subtitle="Every project known to AI Video Studio">
      <Suspense fallback={<p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}>
        <ProjectList />
      </Suspense>
    </PageShell>
  );
}

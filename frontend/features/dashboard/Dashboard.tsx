"use client";

import { useActiveRunsCount } from "@/hooks/useActiveRunsCount";
import { useProjects } from "@/hooks/useProjects";

import { QuickActions } from "./QuickActions";
import { RecentProjects } from "./RecentProjects";
import { SummaryCard } from "./SummaryCards";

export function Dashboard() {
  const { projects, isLoading, error } = useProjects();
  const { count: activeRuns, isLoading: isLoadingActiveRuns } = useActiveRunsCount(projects);

  if (error) {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        Failed to load dashboard data: {error}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SummaryCard label="Total Projects" value={isLoading ? "…" : String(projects.length)} />
        <SummaryCard
          label="Active Runs"
          value={isLoadingActiveRuns || activeRuns === null ? "…" : String(activeRuns)}
          hint="Render & publish runs only - director/producer runs aren't visible here yet"
        />
        <QuickActions />
      </div>
      <RecentProjects projects={projects} />
    </div>
  );
}

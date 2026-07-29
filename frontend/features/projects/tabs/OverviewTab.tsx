import { ActiveRuns } from "@/features/projects/details/ActiveRuns";
import { Overview } from "@/features/projects/details/Overview";
import { ProductionProgress } from "@/features/projects/details/ProductionProgress";
import { RecentActivity } from "@/features/projects/details/RecentActivity";
import { RunControls } from "@/features/runs/RunControls";
import type { Project } from "@/types/project";
import type { PublishStageStatus, RunAccepted, StageStatus } from "@/types/run";

export function OverviewTab({
  project,
  projectId,
  activeRun,
  onRunStarted,
  render,
  publish,
  isLoadingSnapshots,
  onRunTerminal,
}: {
  project: Project;
  projectId: string;
  activeRun: { run: RunAccepted; stageLabel: string } | null;
  onRunStarted: (run: RunAccepted, stageLabel: string) => void;
  render: StageStatus | null;
  publish: PublishStageStatus | null;
  isLoadingSnapshots: boolean;
  onRunTerminal: () => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <Overview project={project} />

      <RunControls projectId={projectId} onRunStarted={onRunStarted} />

      <ActiveRuns
        activeRun={activeRun}
        render={render}
        publish={publish}
        isLoadingSnapshots={isLoadingSnapshots}
        onRunTerminal={onRunTerminal}
      />

      <ProductionProgress status={project.status} />

      <RecentActivity project={project} render={render} publish={publish} />
    </div>
  );
}

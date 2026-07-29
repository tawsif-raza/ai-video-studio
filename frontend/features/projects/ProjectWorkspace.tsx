"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { useProducerPackage } from "@/hooks/useProducerPackage";
import { useProductionPackage } from "@/hooks/useProductionPackage";
import { useProject } from "@/hooks/useProject";
import { useStageSnapshots } from "@/hooks/useStageSnapshots";
import type { RunAccepted } from "@/types/run";

import { CameraPlanTab } from "./tabs/CameraPlanTab";
import { MediaTab } from "./tabs/MediaTab";
import { OverviewTab } from "./tabs/OverviewTab";
import { PromptSetTab } from "./tabs/PromptSetTab";
import { PublishingTab } from "./tabs/PublishingTab";
import { RenderPreviewTab } from "./tabs/RenderPreviewTab";
import { ResearchTab } from "./tabs/ResearchTab";
import { ScenePlanTab } from "./tabs/ScenePlanTab";
import { ShotPlanTab } from "./tabs/ShotPlanTab";
import { StoryTab } from "./tabs/StoryTab";
import { TimelineTab } from "./tabs/TimelineTab";
import { VoiceScriptTab } from "./tabs/VoiceScriptTab";
import { WorkspaceTabs, type WorkspaceTab } from "./WorkspaceTabs";

/**
 * The Interactive Project Workspace (Milestone W8): one tab per pipeline
 * stage, all consuming only the REST/SSE surface W1-W7.5 already built
 * (production-package, producer-package, media, run/status endpoints) plus
 * the one new render/video streaming endpoint this milestone adds. No tab
 * re-derives or re-decides anything the backend already decided - each one
 * renders exactly the structured content its package/endpoint returns.
 */
export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const { project, isLoading, error, refetch } = useProject(projectId);
  const {
    render,
    publish,
    isLoading: isLoadingSnapshots,
    refetch: refetchStageSnapshots,
  } = useStageSnapshots(projectId);
  const { productionPackage, refetch: refetchProductionPackage } = useProductionPackage(projectId);
  const { producerPackage, refetch: refetchProducerPackage } = useProducerPackage(projectId);
  const searchParams = useSearchParams();
  const initialRunId = searchParams.get("runId");

  const [activeTab, setActiveTab] = useState<WorkspaceTab>("Overview");
  const [activeRun, setActiveRun] = useState<{ run: RunAccepted; stageLabel: string } | null>(
    initialRunId
      ? {
          run: { run_id: initialRunId, project_id: projectId, status: "queued" },
          stageLabel: "Director Studio",
        }
      : null,
  );

  if (isLoading) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading project…</p>;
  }
  if (error || !project) {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        Failed to load project: {error ?? "not found"}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <WorkspaceTabs active={activeTab} onChange={setActiveTab} />
      <div>
        {activeTab === "Overview" && (
          <OverviewTab
            project={project}
            projectId={projectId}
            activeRun={activeRun}
            onRunStarted={(run, stageLabel) => setActiveRun({ run, stageLabel })}
            render={render}
            publish={publish}
            isLoadingSnapshots={isLoadingSnapshots}
            onRunTerminal={() => {
              refetch();
              refetchProductionPackage();
              refetchProducerPackage();
              refetchStageSnapshots();
            }}
          />
        )}
        {activeTab === "Research" && <ResearchTab productionPackage={productionPackage} />}
        {activeTab === "Story" && <StoryTab productionPackage={productionPackage} />}
        {activeTab === "Scene Plan" && <ScenePlanTab productionPackage={productionPackage} />}
        {activeTab === "Shot Plan" && <ShotPlanTab productionPackage={productionPackage} />}
        {activeTab === "Camera Plan" && <CameraPlanTab productionPackage={productionPackage} />}
        {activeTab === "Prompt Set" && <PromptSetTab productionPackage={productionPackage} />}
        {activeTab === "Voice Script" && <VoiceScriptTab productionPackage={productionPackage} />}
        {activeTab === "Timeline" && <TimelineTab producerPackage={producerPackage} />}
        {activeTab === "Media" && <MediaTab projectId={projectId} />}
        {activeTab === "Render Preview" && <RenderPreviewTab project={project} />}
        {activeTab === "Publishing" && (
          <PublishingTab
            producerPackage={producerPackage}
            publishStatus={publish}
            activeRun={activeRun ? { runId: activeRun.run.run_id, stageLabel: activeRun.stageLabel } : null}
          />
        )}
      </div>
    </div>
  );
}

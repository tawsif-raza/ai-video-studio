import { MediaPanel } from "@/features/projects/details/MediaPanel";

export function MediaTab({ projectId }: { projectId: string }) {
  return <MediaPanel projectId={projectId} />;
}

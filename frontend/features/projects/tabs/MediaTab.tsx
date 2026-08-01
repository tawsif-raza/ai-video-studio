import { MediaPanel } from "@/features/projects/details/MediaPanel";

export function MediaTab({
  projectId,
  onMediaChanged,
}: {
  projectId: string;
  onMediaChanged?: () => void;
}) {
  return <MediaPanel projectId={projectId} onMediaChanged={onMediaChanged} />;
}

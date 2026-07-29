import { renderVideoUrl } from "@/api/runs";
import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { Project } from "@/types/project";

/**
 * The <video> element's src points directly at GET /projects/{id}/render/video
 * (W8) - never a filesystem path. Whether a video exists is read from
 * project.status (VIDEO_RENDERED) rather than probed with a request first,
 * since that's the same fact the backend itself uses to decide 404
 * (rendered_video_path is only set once VIDEO_RENDERED is reached) - this
 * doesn't duplicate that decision, it just avoids an doomed request when
 * we already know the answer.
 */
export function RenderPreviewTab({ project }: { project: Project }) {
  if (project.status !== "VIDEO_RENDERED") {
    return <EmptyState message="No rendered video yet - run the Execution Engine to completion first." />;
  }

  return (
    <Card>
      <CardTitle>Render Preview</CardTitle>
      <video
        controls
        className="mt-3 w-full max-w-2xl rounded-lg bg-black"
        src={renderVideoUrl(project.project_id)}
      >
        Your browser does not support embedded video.
      </video>
    </Card>
  );
}

import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProducerPackage } from "@/types/package";

export function TimelineTab({ producerPackage }: { producerPackage: ProducerPackage | null }) {
  if (!producerPackage) {
    return <EmptyState message="Producer package not generated yet - run Producer Studio first." />;
  }

  const timeline = producerPackage["timeline_plan.json"];
  if (!timeline) {
    return <EmptyState message="Timeline has not been generated for this project yet." />;
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardTitle>Total Duration</CardTitle>
        <p className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
          {timeline.total_duration_seconds}s
        </p>
      </Card>

      <Card>
        <CardTitle>Clips</CardTitle>
        <ul className="mt-3 flex flex-col gap-2">
          {timeline.clips.map((clip) => (
            <li
              key={`${clip.scene_id}-${clip.shot_id}`}
              className="flex items-center justify-between rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-800/50"
            >
              <span className="font-medium text-zinc-900 dark:text-zinc-50">
                Scene {clip.scene_id}, Shot {clip.shot_id}
              </span>
              <span className="text-zinc-500 dark:text-zinc-400">{clip.asset_type}</span>
              <span className="text-zinc-700 dark:text-zinc-300">
                {clip.start_time}s &ndash; {clip.end_time}s
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardTitle>Voice Segments</CardTitle>
        <ul className="mt-3 flex flex-col gap-2">
          {timeline.voice_segments.map((segment, index) => (
            <li
              key={index}
              className="flex items-center justify-between rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-800/50"
            >
              <span className="font-medium text-zinc-900 dark:text-zinc-50">Scene {segment.scene_id}</span>
              <span className="text-zinc-700 dark:text-zinc-300">
                {segment.start_time}s &ndash; {segment.end_time}s
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

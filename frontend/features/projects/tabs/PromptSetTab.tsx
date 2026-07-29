import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProductionPackage } from "@/types/package";

export function PromptSetTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const imagePrompts = productionPackage["image_prompts.json"];
  const videoPrompts = productionPackage["video_prompts.json"];
  const videoByKey = new Map(videoPrompts.map((v) => [`${v.scene_id}-${v.shot_id}`, v.video_motion_prompt]));

  return (
    <div className="flex flex-col gap-4">
      {imagePrompts.map((prompt) => (
        <Card key={`${prompt.scene_id}-${prompt.shot_id}`}>
          <CardTitle>
            Scene {prompt.scene_id}, Shot {prompt.shot_id}
          </CardTitle>
          <div className="mt-3 flex flex-col gap-3 text-sm">
            <div>
              <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Image Prompt</p>
              <p className="mt-1 text-zinc-700 dark:text-zinc-300">{prompt.image_prompt}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Video Motion Prompt</p>
              <p className="mt-1 text-zinc-700 dark:text-zinc-300">
                {videoByKey.get(`${prompt.scene_id}-${prompt.shot_id}`) ?? "—"}
              </p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

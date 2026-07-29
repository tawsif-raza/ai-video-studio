import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProductionPackage } from "@/types/package";

export function ScenePlanTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const scenes = productionPackage["scene_plan.json"];

  return (
    <div className="flex flex-col gap-4">
      {scenes.map((scene) => (
        <Card key={scene.scene_id}>
          <div className="flex items-center justify-between">
            <CardTitle>
              Scene {scene.scene_id}: {scene.title}
            </CardTitle>
            <span className="text-xs text-zinc-400 dark:text-zinc-500">{scene.estimated_duration_seconds}s</span>
          </div>
          <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{scene.summary}</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Setting</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{scene.setting}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Mood</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{scene.mood}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-400 dark:text-zinc-500">Characters</dt>
              <dd className="text-zinc-900 dark:text-zinc-50">{scene.characters_present.join(", ")}</dd>
            </div>
          </dl>
        </Card>
      ))}
    </div>
  );
}

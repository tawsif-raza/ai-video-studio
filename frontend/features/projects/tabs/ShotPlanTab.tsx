import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProductionPackage } from "@/types/package";

export function ShotPlanTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const scenePlans = productionPackage["shot_plan.json"];

  return (
    <div className="flex flex-col gap-4">
      {scenePlans.map((scenePlan) => (
        <Card key={scenePlan.scene_id}>
          <CardTitle>Scene {scenePlan.scene_id}</CardTitle>
          <ul className="mt-3 flex flex-col gap-3">
            {scenePlan.shots.map((shot) => (
              <li key={shot.shot_id} className="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/50">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-zinc-900 dark:text-zinc-50">Shot {shot.shot_id}</span>
                  <span className="text-xs text-zinc-400 dark:text-zinc-500">{shot.duration_seconds}s</span>
                </div>
                <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">{shot.description}</p>
                <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                  Characters: {shot.characters_in_shot.join(", ") || "none"}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

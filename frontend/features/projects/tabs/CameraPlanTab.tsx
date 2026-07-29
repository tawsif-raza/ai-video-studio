import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProductionPackage } from "@/types/package";

export function CameraPlanTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const scenePlans = productionPackage["camera_plan.json"];

  return (
    <div className="flex flex-col gap-4">
      {scenePlans.map((scenePlan) => (
        <Card key={scenePlan.scene_id}>
          <CardTitle>Scene {scenePlan.scene_id}</CardTitle>
          <ul className="mt-3 flex flex-col gap-2">
            {scenePlan.shots.map((shot) => (
              <li
                key={shot.shot_id}
                className="flex items-center justify-between rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-800/50"
              >
                <span className="font-medium text-zinc-900 dark:text-zinc-50">Shot {shot.shot_id}</span>
                <span className="text-zinc-700 dark:text-zinc-300">{shot.camera_angle}</span>
                <span className="text-zinc-500 dark:text-zinc-400">{shot.camera_movement}</span>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

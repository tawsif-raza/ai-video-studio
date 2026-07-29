import { Card, CardTitle } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { isResearchSkipped } from "@/types/package";
import type { ProductionPackage } from "@/types/package";

export function ResearchTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const brief = productionPackage["research_brief.json"];

  if (isResearchSkipped(brief)) {
    return <EmptyState message={`Research was skipped for this project: ${brief.reason}`} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardTitle>Key Facts</CardTitle>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
          {brief.key_facts.map((fact, index) => (
            <li key={index}>{fact}</li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardTitle>Considerations</CardTitle>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
          {brief.considerations.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

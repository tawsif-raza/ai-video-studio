import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProductionPackage } from "@/types/package";

export function VoiceScriptTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const voiceScript = productionPackage["voice_script.txt"];
  const isPending = voiceScript.trimStart().startsWith("#");

  if (isPending) {
    return <EmptyState message="Voice script has not been generated for this project yet." />;
  }

  return (
    <Card>
      <div className="flex flex-col gap-3">
        {voiceScript.split("\n\n").map((paragraph, index) => (
          <p key={index} className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {paragraph}
          </p>
        ))}
      </div>
    </Card>
  );
}

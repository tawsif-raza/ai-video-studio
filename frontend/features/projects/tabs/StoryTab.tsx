import { Fragment } from "react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { ProductionPackage } from "@/types/package";

/**
 * A small renderer for story.md's specific, known template
 * (project_manager/package_writer.py's _build_story_markdown) - headers,
 * bold runs, and "- " list items - not a general-purpose markdown parser.
 * Anything outside that known shape still renders safely as a plain
 * paragraph.
 */
function renderStoryLine(line: string, key: number) {
  if (line.startsWith("### ")) {
    return (
      <h3 key={key} className="mt-3 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
        {line.slice(4)}
      </h3>
    );
  }
  if (line.startsWith("## ")) {
    return (
      <h2 key={key} className="mt-4 text-base font-semibold text-zinc-900 dark:text-zinc-50">
        {line.slice(3)}
      </h2>
    );
  }
  if (line.startsWith("# ")) {
    return (
      <h1 key={key} className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
        {line.slice(2)}
      </h1>
    );
  }
  if (line.startsWith("- ")) {
    return (
      <p key={key} className="ml-4 text-sm text-zinc-700 dark:text-zinc-300">
        &bull; {renderBold(line.slice(2))}
      </p>
    );
  }
  if (!line.trim()) {
    return <div key={key} className="h-2" />;
  }
  return (
    <p key={key} className="text-sm text-zinc-700 dark:text-zinc-300">
      {renderBold(line)}
    </p>
  );
}

function renderBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={index}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  );
}

export function StoryTab({ productionPackage }: { productionPackage: ProductionPackage | null }) {
  if (!productionPackage) {
    return <EmptyState message="Production package not generated yet - run Director Studio first." />;
  }

  const story = productionPackage["story.md"];

  return (
    <Card>
      <div className="flex flex-col gap-1">{story.split("\n").map((line, index) => renderStoryLine(line, index))}</div>
    </Card>
  );
}

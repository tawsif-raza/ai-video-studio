"use client";

const TABS = [
  "Overview",
  "Research",
  "Story",
  "Scene Plan",
  "Shot Plan",
  "Camera Plan",
  "Prompt Set",
  "Voice Script",
  "Timeline",
  "Media",
  "Render Preview",
  "Publishing",
] as const;

export type WorkspaceTab = (typeof TABS)[number];

export function WorkspaceTabs({
  active,
  onChange,
}: {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
}) {
  return (
    <div
      role="tablist"
      className="flex gap-1 overflow-x-auto border-b border-zinc-200 dark:border-zinc-800"
    >
      {TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={active === tab}
          onClick={() => onChange(tab)}
          className={`shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
            active === tab
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

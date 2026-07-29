import type { ReactNode } from "react";

import { Sidebar } from "@/components/layout/Sidebar";

/**
 * The persistent chrome (Sidebar + main content area) that wraps every
 * page, defined once in app/layout.tsx so it never remounts on
 * navigation. Header is rendered per-page (via PageShell below) since its
 * title/subtitle are page-specific, but its position in the layout is
 * fixed and consistent everywhere.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-zinc-50 dark:bg-zinc-950">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}

import type { ReactNode } from "react";

import { Header } from "@/components/layout/Header";

/** Per-page Header + scrollable main content area, used inside AppShell. */
export function PageShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <>
      <Header title={title} subtitle={subtitle} />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </>
  );
}

"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { Sidebar } from "@/components/layout/Sidebar";
import { isAuthRoute } from "@/features/auth/ProtectedRoute";

/**
 * The persistent chrome (Sidebar + main content area) that wraps dashboard
 * pages, defined once in app/layout.tsx so it never remounts on navigation.
 * Auth routes (e.g. /login, /signup, /forgot-password, /reset-password)
 * bypass the sidebar chrome for a dedicated full-screen layout.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isAuth = isAuthRoute(pathname || "");

  if (isAuth) {
    return <main className="min-h-screen w-full bg-zinc-950 text-zinc-100">{children}</main>;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-50 dark:bg-zinc-950">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}


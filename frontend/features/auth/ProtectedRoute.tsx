"use client";

import {
  useEffect,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/features/auth/AuthContext";

/**
 * Returns true if the pathname is an authentication route (e.g. /login, /signup).
 */
export function isAuthRoute(pathname: string): boolean {
  return (
    pathname === "/login" ||
    pathname.startsWith("/login/") ||
    pathname === "/signup" ||
    pathname.startsWith("/signup/") ||
    pathname === "/forgot-password" ||
    pathname.startsWith("/forgot-password/") ||
    pathname === "/reset-password" ||
    pathname.startsWith("/reset-password/")
  );
}

/**
 * Ensures destination URLs are valid, relative paths and do not create redirect loops.
 * Protects against open-redirect attacks and recursive redirects back to auth routes.
 */
export function sanitizeDestination(url: string | null | undefined): string {
  if (!url) return "/";
  const trimmed = url.trim();
  // Must be a relative path starting with / and not // (protocol-relative URL)
  if (!trimmed.startsWith("/") || trimmed.startsWith("//")) return "/";
  // Strip query/hash before evaluating route identity
  const pathPart = trimmed.split("?")[0].split("#")[0];
  if (isAuthRoute(pathPart)) return "/";
  return trimmed;
}

/**
 * Reads destination parameter from window query string if present in browser.
 */
export function getRedirectDestination(): string | null {
  if (typeof window === "undefined") return null;
  const searchParams = new URLSearchParams(window.location.search);
  const next = searchParams.get("next") || searchParams.get("redirect");
  return next ? sanitizeDestination(next) : null;
}

export interface ProtectedRouteProps {
  children: ReactNode;
  publicRoutes?: string[];
  fallback?: ReactNode;
}

/**
 * Route guard component that:
 * 1. Waits for authentication hydration/session check (never redirects while isLoading)
 * 2. Redirects unauthenticated users trying to access protected routes to /login?next=...
 * 3. Redirects authenticated users trying to access /login or /signup to / or their requested target
 * 4. Prevents flashing protected content to unauthenticated users or login forms to authenticated users
 */
export function ProtectedRoute({
  children,
  publicRoutes = [],
  fallback,
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const pathname = usePathname() || "/";
  const router = useRouter();

  const isAuth = isAuthRoute(pathname);
  const isPublic = publicRoutes.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );

  useEffect(() => {
    // Critical: Never redirect while session is still loading
    if (isLoading) return;

    if (isAuth && isAuthenticated) {
      // Authenticated user attempting to visit login/signup -> send to dashboard/next
      const dest = getRedirectDestination() || "/";
      router.replace(dest);
    } else if (!isAuth && !isPublic && !isAuthenticated) {
      // Unauthenticated user attempting to visit protected area -> send to login with destination
      const fullPath =
        typeof window !== "undefined"
          ? window.location.pathname + window.location.search
          : pathname;
      const targetParam = encodeURIComponent(fullPath);
      router.replace(`/login?next=${targetParam}`);
    }
  }, [isLoading, isAuthenticated, isAuth, isPublic, pathname, router]);

  // While session state is loading: display cinematic loading splash (no content flash)
  if (isLoading) {
    return (
      fallback || (
        <div
          role="status"
          aria-label="Loading studio session"
          className="flex min-h-screen w-full flex-col items-center justify-center bg-zinc-950 text-zinc-400"
        >
          <div className="flex flex-col items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-indigo-500/30 bg-indigo-950/40 text-indigo-400 shadow-lg">
              <svg
                className="h-6 w-6 animate-pulse"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <rect x="2" y="2" width="20" height="20" rx="4" />
                <path d="m10 8 6 4-6 4V8z" fill="currentColor" stroke="none" />
              </svg>
            </div>
            <div className="flex items-center gap-2 text-xs font-medium tracking-wide text-zinc-400">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
              <span>Loading studio session...</span>
            </div>
          </div>
        </div>
      )
    );
  }

  // Prevent flashing login/signup forms while redirecting an authenticated user
  if (isAuth && isAuthenticated) {
    return (
      <div
        role="status"
        aria-label="Redirecting to studio"
        className="flex min-h-screen w-full items-center justify-center bg-zinc-950 text-zinc-400"
      >
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  // Prevent flashing protected dashboards/projects while redirecting an unauthenticated user
  if (!isAuth && !isPublic && !isAuthenticated) {
    return (
      <div
        role="status"
        aria-label="Redirecting to sign in"
        className="flex min-h-screen w-full items-center justify-center bg-zinc-950 text-zinc-400"
      >
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}

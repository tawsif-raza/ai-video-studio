"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { NotificationArea } from "@/components/layout/NotificationArea";
import { StatusIndicator } from "@/components/layout/StatusIndicator";
import { useAuth } from "@/features/auth/AuthContext";

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const router = useRouter();

  const handleSignOut = async () => {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  };

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 dark:border-zinc-800 dark:bg-zinc-950">
      <div>
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{title}</h1>
        {subtitle && <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">
        <StatusIndicator />
        <NotificationArea />

        {!isLoading && (
          isAuthenticated && user ? (
            <div className="flex items-center gap-2 border-l border-zinc-200 pl-3 dark:border-zinc-800">
              <div
                className="flex h-8 w-8 items-center justify-center rounded-full border border-indigo-500/30 bg-indigo-50 text-xs font-semibold text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                title={user.email}
                aria-label={`User avatar for ${user.full_name || user.email}`}
              >
                {(user.full_name ? user.full_name.charAt(0) : user.email.charAt(0)).toUpperCase()}
              </div>
              <div className="hidden flex-col sm:flex">
                <span className="max-w-[140px] truncate text-xs font-medium text-zinc-900 dark:text-zinc-100">
                  {user.full_name || user.email}
                </span>
                <span className="max-w-[140px] truncate text-[10px] text-zinc-500 dark:text-zinc-400">
                  {user.email}
                </span>
              </div>
              <button
                type="button"
                onClick={handleSignOut}
                aria-label="Sign out"
                title="Sign out of your account"
                className="ml-1 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-red-600 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="2"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75"
                  />
                </svg>
                <span className="hidden md:inline">Sign out</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center border-l border-zinc-200 pl-3 dark:border-zinc-800">
              <Link
                href="/login"
                className="inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-100 hover:text-indigo-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-indigo-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              >
                Sign In
              </Link>
            </div>
          )
        )}
      </div>
    </header>
  );
}

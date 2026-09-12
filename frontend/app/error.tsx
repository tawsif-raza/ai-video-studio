"use client";

import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log the error to an error reporting service in production
    console.error("Global Error Caught:", error);
  }, [error]);

  return (
    <div className="flex h-full min-h-screen w-full flex-col items-center justify-center bg-zinc-950 p-8 text-zinc-100">
      <div className="max-w-md space-y-4 rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center">
        <h2 className="text-xl font-semibold text-red-400">Something went wrong</h2>
        <p className="text-sm text-zinc-400">
          An unexpected error occurred in the application. Our team has been notified.
        </p>
        <button
          onClick={() => reset()}
          className="mt-4 rounded-md bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-700 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

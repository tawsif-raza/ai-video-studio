"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Fatal Global Error Caught:", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="h-full bg-zinc-950 text-zinc-100">
        <div className="flex h-full min-h-screen w-full flex-col items-center justify-center p-8">
          <div className="max-w-md space-y-4 rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center">
            <h2 className="text-xl font-semibold text-red-400">Fatal Application Error</h2>
            <p className="text-sm text-zinc-400">
              The application encountered a critical failure.
            </p>
            <button
              onClick={() => reset()}
              className="mt-4 rounded-md bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-700 transition-colors"
            >
              Reload application
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}

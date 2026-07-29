import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/Card";

export function QuickActions() {
  return (
    <Card>
      <CardTitle>Quick Actions</CardTitle>
      <div className="mt-3 flex flex-col gap-2">
        <Link
          href="/projects?new=1"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-center text-sm font-medium text-white hover:bg-indigo-500"
        >
          New Project
        </Link>
        <Link
          href="/projects"
          className="rounded-lg bg-zinc-100 px-4 py-2 text-center text-sm font-medium text-zinc-900 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700"
        >
          View All Projects
        </Link>
      </div>
    </Card>
  );
}

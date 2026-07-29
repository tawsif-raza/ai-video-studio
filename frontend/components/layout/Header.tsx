import { NotificationArea } from "@/components/layout/NotificationArea";
import { StatusIndicator } from "@/components/layout/StatusIndicator";

export function Header({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 dark:border-zinc-800 dark:bg-zinc-950">
      <div>
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{title}</h1>
        {subtitle && <p className="text-xs text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">
        <StatusIndicator />
        <NotificationArea />
      </div>
    </header>
  );
}

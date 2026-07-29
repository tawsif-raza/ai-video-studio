import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/Card";

export default function SettingsPage() {
  return (
    <PageShell title="Settings">
      <Card>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Settings aren&rsquo;t implemented yet. This page is a placeholder, per Milestone W7&rsquo;s scope - no
          authentication or user accounts exist in this system yet either.
        </p>
      </Card>
    </PageShell>
  );
}

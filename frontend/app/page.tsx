import { PageShell } from "@/components/layout/PageShell";
import { Dashboard } from "@/features/dashboard/Dashboard";

export default function DashboardPage() {
  return (
    <PageShell title="Dashboard" subtitle="Overview of all AI Video Studio projects">
      <Dashboard />
    </PageShell>
  );
}

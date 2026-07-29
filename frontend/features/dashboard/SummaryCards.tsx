import { Card, CardTitle } from "@/components/ui/Card";

export function SummaryCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardTitle>{label}</CardTitle>
      <p className="mt-2 text-3xl font-semibold text-zinc-900 dark:text-zinc-50">{value}</p>
      {hint && <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">{hint}</p>}
    </Card>
  );
}

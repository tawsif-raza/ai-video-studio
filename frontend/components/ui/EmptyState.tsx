import { Card } from "@/components/ui/Card";

export function EmptyState({ message }: { message: string }) {
  return (
    <Card>
      <p className="text-sm text-zinc-500 dark:text-zinc-400">{message}</p>
    </Card>
  );
}

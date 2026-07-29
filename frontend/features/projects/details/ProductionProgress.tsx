import { Card, CardTitle } from "@/components/ui/Card";
import { PROJECT_STATE_ORDER, type ProjectState } from "@/types/project";

/**
 * A simple linear stepper over ProjectState's pipeline order - a
 * presentational simplification, not a reimplementation of the state
 * machine. RESEARCHED is skippable (--skip-research), so a project can
 * legitimately be "ahead" of a step this stepper marks incomplete; that's
 * a known, acceptable simplification for a shell-milestone progress view.
 */
export function ProductionProgress({ status }: { status: ProjectState }) {
  const currentIndex = PROJECT_STATE_ORDER.indexOf(status);

  return (
    <Card>
      <CardTitle>Production Progress</CardTitle>
      <ol className="mt-4 flex flex-col gap-1.5">
        {PROJECT_STATE_ORDER.map((state, index) => {
          const done = index < currentIndex;
          const current = index === currentIndex;
          return (
            <li key={state} className="flex items-center gap-2 text-sm">
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  current
                    ? "bg-indigo-600"
                    : done
                      ? "bg-emerald-500"
                      : "bg-zinc-200 dark:bg-zinc-700"
                }`}
                aria-hidden="true"
              />
              <span
                className={
                  current
                    ? "font-medium text-zinc-900 dark:text-zinc-50"
                    : done
                      ? "text-zinc-500 dark:text-zinc-400"
                      : "text-zinc-400 dark:text-zinc-600"
                }
              >
                {state.replaceAll("_", " ")}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

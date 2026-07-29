/**
 * Placeholder per Milestone W7's scope ("Notification area (placeholder)")
 * - no toast/alert system is implemented yet. A future milestone can wire
 * this up to Run failures/completions without changing the layout shape.
 */
export function NotificationArea() {
  return (
    <button
      type="button"
      disabled
      className="rounded-full p-2 text-zinc-400 dark:text-zinc-600"
      title="Notifications (coming soon)"
      aria-label="Notifications (coming soon)"
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" strokeWidth={1.5} stroke="currentColor" className="h-5 w-5">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
        />
      </svg>
    </button>
  );
}

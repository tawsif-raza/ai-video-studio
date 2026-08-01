"use client";

import { Button } from "@/components/ui/Button";

/**
 * Milestone W10: a small, reusable confirmation dialog - used by the Media
 * tab's single-delete and bulk-delete actions (requirements #1/#3 both
 * require confirmation before a destructive delete). Deliberately not a
 * generic modal system (portal/focus-trap library, stacking context
 * manager) - a single centered overlay is all either caller needs, and
 * building more would be scope this milestone doesn't ask for.
 */
export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  isConfirming = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isConfirming?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          {title}
        </h2>
        <p id="confirm-dialog-message" className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          {message}
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={isConfirming}>
            {cancelLabel}
          </Button>
          <Button variant="danger" onClick={onConfirm} isLoading={isConfirming}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

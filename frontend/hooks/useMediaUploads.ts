"use client";

import { useCallback, useRef, useState } from "react";

import { uploadMediaWithProgress } from "@/api/projects";

export type UploadItemStatus = "pending" | "uploading" | "done" | "error";

export interface UploadItem {
  id: string;
  name: string;
  size: number;
  loaded: number;
  status: UploadItemStatus;
  error?: string;
}

/**
 * Milestone W10 requirement #5: "configurable concurrency limit (avoid
 * exhausting memory)". A named, exported constant rather than a user-facing
 * control - this app has no per-user settings store to hang a control on
 * (WEB_DASHBOARD_ARCHITECTURE.md SS7.6: no user/account concept at all),
 * and useMediaUploads's `concurrency` parameter already lets any caller
 * override it. 4 concurrent in-flight uploads is enough to saturate a
 * typical connection without opening 100 sockets/canvases at once for a
 * large batch (the actual memory-pressure risk: each in-flight upload also
 * holds a decoded, possibly-recompressed image in memory client-side).
 */
export const DEFAULT_UPLOAD_CONCURRENCY = 4;

interface UseMediaUploadsResult {
  uploads: UploadItem[];
  isUploading: boolean;
  overallProgress: { loaded: number; total: number };
  speedBytesPerSecond: number;
  etaSeconds: number | null;
  startUpload: (
    files: File[],
    prepare?: (file: File) => Promise<File>,
  ) => Promise<{ succeeded: number; failed: number }>;
  clearUploads: () => void;
}

/**
 * Drives a batch of concurrent uploads through a small worker pool (at most
 * `concurrency` requests in flight at once, regardless of batch size) and
 * tracks per-file + overall progress for the dashboard's upload UI.
 * Continues uploading the remaining files if one fails (requirement #5) -
 * a rejected upload is caught inside the worker loop, not allowed to abort
 * the whole batch.
 */
export function useMediaUploads(
  projectId: string,
  concurrency: number = DEFAULT_UPLOAD_CONCURRENCY,
): UseMediaUploadsResult {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [overallProgress, setOverallProgress] = useState({ loaded: 0, total: 0 });
  const [speedBytesPerSecond, setSpeedBytesPerSecond] = useState(0);
  const idCounter = useRef(0);
  const uploadStartedAt = useRef<number | null>(null);
  const itemsRef = useRef<UploadItem[]>([]);

  const recomputeOverall = useCallback(() => {
    const totals = itemsRef.current.reduce(
      (acc, item) => ({ loaded: acc.loaded + item.loaded, total: acc.total + item.size }),
      { loaded: 0, total: 0 },
    );
    setOverallProgress(totals);

    const startedAt = uploadStartedAt.current;
    if (startedAt !== null) {
      const elapsedSeconds = (Date.now() - startedAt) / 1000;
      setSpeedBytesPerSecond(elapsedSeconds > 0 ? totals.loaded / elapsedSeconds : 0);
    }
  }, []);

  const updateItem = useCallback(
    (id: string, patch: Partial<UploadItem>) => {
      itemsRef.current = itemsRef.current.map((item) => (item.id === id ? { ...item, ...patch } : item));
      setUploads(itemsRef.current);
      recomputeOverall();
    },
    [recomputeOverall],
  );

  const startUpload = useCallback(
    async (files: File[], prepare?: (file: File) => Promise<File>) => {
      if (files.length === 0) return { succeeded: 0, failed: 0 };

      const items: UploadItem[] = files.map((file) => ({
        id: `${Date.now()}-${idCounter.current++}`,
        name: file.name,
        size: file.size,
        loaded: 0,
        status: "pending",
      }));
      itemsRef.current = items;
      setUploads(items);
      setOverallProgress({ loaded: 0, total: items.reduce((sum, item) => sum + item.size, 0) });
      setSpeedBytesPerSecond(0);
      uploadStartedAt.current = Date.now();
      setIsUploading(true);

      let succeeded = 0;
      let failed = 0;
      let cursor = 0;

      const worker = async () => {
        while (cursor < files.length) {
          const index = cursor++;
          const item = items[index];
          const file = files[index];
          updateItem(item.id, { status: "uploading" });
          try {
            const prepared = prepare ? await prepare(file) : file;
            updateItem(item.id, { size: prepared.size });
            await uploadMediaWithProgress(projectId, prepared, (loadedBytes, totalBytes) => {
              updateItem(item.id, { loaded: loadedBytes, size: totalBytes || prepared.size });
            });
            updateItem(item.id, { status: "done" });
            succeeded++;
          } catch (err) {
            updateItem(item.id, {
              status: "error",
              error: err instanceof Error ? err.message : String(err),
            });
            failed++;
          }
        }
      };

      const workerCount = Math.max(1, Math.min(concurrency, files.length));
      await Promise.all(Array.from({ length: workerCount }, () => worker()));

      uploadStartedAt.current = null;
      setIsUploading(false);
      return { succeeded, failed };
    },
    [projectId, concurrency, updateItem],
  );

  const clearUploads = useCallback(() => {
    itemsRef.current = [];
    setUploads([]);
    setOverallProgress({ loaded: 0, total: 0 });
    setSpeedBytesPerSecond(0);
  }, []);

  const etaSeconds =
    speedBytesPerSecond > 0 && overallProgress.total > overallProgress.loaded
      ? (overallProgress.total - overallProgress.loaded) / speedBytesPerSecond
      : null;

  return { uploads, isUploading, overallProgress, speedBytesPerSecond, etaSeconds, startUpload, clearUploads };
}

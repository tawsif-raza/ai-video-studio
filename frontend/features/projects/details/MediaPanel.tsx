"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { bulkDeleteMedia, deleteMedia, getProjectMedia } from "@/api/projects";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useMediaUploads } from "@/hooks/useMediaUploads";
import {
  MEDIA_MANIFEST_FIELD_TO_CATEGORY,
  type ImportedMediaManifest,
  type MediaCategory,
  type ScannedMediaFile,
} from "@/types/media";

// A common renaming mistake when "hide known extensions" is on: typing the
// full desired name (including ".png") onto a file whose original extension
// is reappended automatically, producing "scene_5_shot_11.png.png" - which
// silently fails the backend's scene_<id>_shot_<id>.<ext> naming check
// with no explanation. Collapse an exact doubled extension before upload.
function fixDuplicateExtension(filename: string): string {
  const match = filename.match(/^(.*)\.([A-Za-z0-9]+)\.\2$/i);
  return match ? `${match[1]}.${match[2]}` : filename;
}

// AI-generated source images are commonly several MB each and far larger
// than any render resolution this app produces (1080p/720p) - the render
// filter graph scales every image down to the target frame regardless
// (execution_engine/filter_graph_builder.py's _normalize_expr), so uploading
// the original resolution buys zero output quality, only slower uploads.
// Downscale to a generous cap and re-encode as JPEG before sending; this is
// the dominant lever for "uploads feel slow" once requests are concurrent,
// since total upload time on a mobile connection is bytes-over-bandwidth,
// not request count.
const MAX_DIMENSION = 1920;
const JPEG_QUALITY = 0.85;
const SKIP_COMPRESSION_BELOW_BYTES = 400 * 1024;

async function prepareForUpload(file: File): Promise<File> {
  const fixedName = fixDuplicateExtension(file.name);
  const isImage = /\.(png|jpe?g)$/i.test(fixedName);
  const renamed = fixedName === file.name ? file : new File([file], fixedName, { type: file.type });

  if (!isImage || file.size <= SKIP_COMPRESSION_BELOW_BYTES) {
    return renamed;
  }

  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_DIMENSION / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return renamed;
    ctx.drawImage(bitmap, 0, 0, width, height);

    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
    if (!blob || blob.size >= file.size) {
      // Compression didn't actually help (rare) - upload the original rather
      // than a "smaller" file that's actually bigger or a canvas artifact.
      return renamed;
    }
    return new File([blob], fixedName.replace(/\.(png|jpe?g)$/i, ".jpg"), { type: "image/jpeg" });
  } catch {
    // Best-effort optimization only - if decoding/encoding fails for any
    // reason, fall back to uploading the original file rather than blocking
    // the upload entirely.
    return renamed;
  }
}

function formatBytes(bytes: number): string {
  return `${Math.round(bytes / 1024)} KB`;
}

function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.ceil(seconds % 60);
  return `${minutes}m ${secs}s`;
}

interface MediaItem {
  key: string; // `${category}:${filename}` - stable, unique across all three categories
  category: MediaCategory;
  file: ScannedMediaFile;
}

function flattenManifest(manifest: ImportedMediaManifest): MediaItem[] {
  return (
    [
      ["images", manifest.images],
      ["videos", manifest.videos],
      ["audio", manifest.audio],
    ] as const
  ).flatMap(([field, files]) => {
    const category = MEDIA_MANIFEST_FIELD_TO_CATEGORY[field];
    return files.map((file) => ({ key: `${category}:${file.filename}`, category, file }));
  });
}

function MediaSection({
  label,
  items,
  selected,
  onToggle,
  onDeleteOne,
}: {
  label: string;
  items: MediaItem[];
  selected: Set<string>;
  onToggle: (key: string) => void;
  onDeleteOne: (item: MediaItem) => void;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label} ({items.length})
      </p>
      {items.length === 0 ? (
        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">None uploaded</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5">
          {items.map((item) => (
            <li key={item.key} className="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-300">
              <input
                type="checkbox"
                aria-label={`Select ${item.file.filename}`}
                checked={selected.has(item.key)}
                onChange={() => onToggle(item.key)}
                className="h-3.5 w-3.5 shrink-0"
              />
              <span className="truncate">
                {item.file.filename} <span className="text-zinc-400">({formatBytes(item.file.size_bytes)})</span>
              </span>
              <button
                type="button"
                aria-label={`Delete ${item.file.filename}`}
                onClick={() => onDeleteOne(item)}
                className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MediaPanel({
  projectId,
  onMediaChanged,
}: {
  projectId: string;
  onMediaChanged?: () => void;
}) {
  const [manifest, setManifest] = useState<ImportedMediaManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<MediaItem | null>(null);
  const [pendingBulkDelete, setPendingBulkDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { uploads, isUploading, overallProgress, speedBytesPerSecond, etaSeconds, startUpload, clearUploads } =
    useMediaUploads(projectId);

  const load = useCallback(() => {
    return getProjectMedia(projectId)
      .then((result) => {
        setManifest(result);
        // Dropping selections for files that no longer exist (deleted from
        // another tab/session, or just removed by this one) keeps "N
        // selected" honest rather than counting phantom items.
        setSelected((prev) => {
          const stillPresent = new Set(flattenManifest(result).map((item) => item.key));
          const next = new Set([...prev].filter((key) => stillPresent.has(key)));
          return next.size === prev.size ? prev : next;
        });
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load media"));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const items = useMemo(() => (manifest ? flattenManifest(manifest) : []), [manifest]);
  const itemsByCategory = useMemo(
    () => ({
      images: items.filter((item) => item.category === "images"),
      video: items.filter((item) => item.category === "video"),
      audio: items.filter((item) => item.category === "audio"),
    }),
    [items],
  );

  const toggleSelected = useCallback((key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => setSelected(new Set(items.map((item) => item.key))), [items]);
  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const refreshAfterChange = useCallback(async () => {
    await load();
    onMediaChanged?.();
  }, [load, onMediaChanged]);

  const handleUpload = async () => {
    const files = fileInputRef.current?.files;
    if (!files || files.length === 0) return;

    setError(null);
    // Files are compressed/renamed client-side (prepareForUpload) and sent
    // through a bounded-concurrency worker pool (useMediaUploads) rather
    // than all at once - unbounded concurrency was the previous behavior
    // and doesn't scale past a handful of files (too many sockets/canvases
    // in flight at once for a 50-100 image batch).
    const { failed } = await startUpload(Array.from(files), prepareForUpload);
    if (failed > 0) {
      setError(`${failed} of ${files.length} file(s) failed to upload - see details below.`);
    } else if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    await refreshAfterChange();
  };

  const confirmDeleteOne = async () => {
    if (!pendingDelete) return;
    setIsDeleting(true);
    setError(null);
    try {
      await deleteMedia(projectId, pendingDelete.category, pendingDelete.file.filename);
      await refreshAfterChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete media file");
    } finally {
      setIsDeleting(false);
      setPendingDelete(null);
    }
  };

  const confirmBulkDelete = async () => {
    const targets = items.filter((item) => selected.has(item.key));
    if (targets.length === 0) {
      setPendingBulkDelete(false);
      return;
    }
    setIsDeleting(true);
    setError(null);
    try {
      const response = await bulkDeleteMedia(
        projectId,
        targets.map((item) => ({ category: item.category, filename: item.file.filename })),
      );
      const failures = response.results.filter((r) => !r.success);
      if (failures.length > 0) {
        setError(
          `${failures.length} of ${targets.length} file(s) could not be deleted: ` +
            failures.map((f) => f.filename).join(", "),
        );
      }
      clearSelection();
      await refreshAfterChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk delete failed");
    } finally {
      setIsDeleting(false);
      setPendingBulkDelete(false);
    }
  };

  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Media</CardTitle>
        <span className="text-xs text-zinc-400 dark:text-zinc-500">{items.length} total file(s)</span>
      </div>

      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {manifest && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-b border-zinc-100 pb-3 dark:border-zinc-800">
            <Button variant="secondary" onClick={selectAll} disabled={items.length === 0}>
              Select All
            </Button>
            <Button variant="secondary" onClick={clearSelection} disabled={selected.size === 0}>
              Clear Selection
            </Button>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">{selected.size} selected</span>
            <Button
              variant="danger"
              onClick={() => setPendingBulkDelete(true)}
              disabled={selected.size === 0}
              className="ml-auto"
            >
              Delete Selected
            </Button>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <MediaSection
              label="Images"
              items={itemsByCategory.images}
              selected={selected}
              onToggle={toggleSelected}
              onDeleteOne={setPendingDelete}
            />
            <MediaSection
              label="Videos"
              items={itemsByCategory.video}
              selected={selected}
              onToggle={toggleSelected}
              onDeleteOne={setPendingDelete}
            />
            <MediaSection
              label="Audio"
              items={itemsByCategory.audio}
              selected={selected}
              onToggle={toggleSelected}
              onDeleteOne={setPendingDelete}
            />
          </div>
        </>
      )}

      <div className="mt-4 flex items-center gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.mp4,.mov,.wav,.mp3,.m4a"
          className="text-xs text-zinc-500 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-zinc-900 dark:text-zinc-400 dark:file:bg-zinc-800 dark:file:text-zinc-100"
        />
        <Button onClick={handleUpload} isLoading={isUploading} variant="secondary">
          Upload
        </Button>
        {uploads.length > 0 && !isUploading && (
          <Button variant="secondary" onClick={clearUploads}>
            Clear Upload List
          </Button>
        )}
      </div>

      {uploads.length > 0 && (
        <div className="mt-3 flex flex-col gap-2 rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/50">
          <div>
            <div className="flex items-center justify-between text-xs text-zinc-600 dark:text-zinc-300">
              <span>
                Overall: {formatBytes(overallProgress.loaded)} / {formatBytes(overallProgress.total)}
              </span>
              <span className="text-zinc-400">
                {speedBytesPerSecond > 0 && `${formatBytes(speedBytesPerSecond)}/s`}
                {etaSeconds !== null && ` · ${formatSeconds(etaSeconds)} remaining`}
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
              <div
                className="h-full rounded-full bg-indigo-600 transition-all"
                style={{
                  width: `${overallProgress.total > 0 ? Math.round((overallProgress.loaded / overallProgress.total) * 100) : 0}%`,
                }}
              />
            </div>
          </div>

          <ul className="flex flex-col gap-1.5">
            {uploads.map((item) => (
              <li key={item.id} className="text-xs">
                <div className="flex items-center justify-between text-zinc-600 dark:text-zinc-300">
                  <span className="truncate">{item.name}</span>
                  <span
                    className={
                      item.status === "error"
                        ? "text-red-600 dark:text-red-400"
                        : item.status === "done"
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-zinc-400"
                    }
                  >
                    {item.status === "error" ? (item.error ?? "Failed") : item.status}
                  </span>
                </div>
                <div className="mt-0.5 h-1 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
                  <div
                    className={`h-full rounded-full transition-all ${item.status === "error" ? "bg-red-500" : "bg-indigo-500"}`}
                    style={{
                      width: `${item.size > 0 ? Math.round((item.loaded / item.size) * 100) : item.status === "done" ? 100 : 0}%`,
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete media file?"
          message={`This permanently deletes "${pendingDelete.file.filename}" from the project. This cannot be undone.`}
          isConfirming={isDeleting}
          onConfirm={confirmDeleteOne}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {pendingBulkDelete && (
        <ConfirmDialog
          title="Delete selected media files?"
          message={`This permanently deletes ${selected.size} file(s) from the project. This cannot be undone.`}
          isConfirming={isDeleting}
          onConfirm={confirmBulkDelete}
          onCancel={() => setPendingBulkDelete(false)}
        />
      )}
    </Card>
  );
}

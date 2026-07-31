"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getProjectMedia, uploadMedia } from "@/api/projects";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import type { ImportedMediaManifest } from "@/types/media";

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

function FileList({ label, files }: { label: string; files: { filename: string; size_bytes: number }[] }) {
  return (
    <div>
      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label} ({files.length})
      </p>
      {files.length === 0 ? (
        <p className="text-xs text-zinc-400 dark:text-zinc-600">None uploaded</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-0.5">
          {files.map((f) => (
            <li key={f.filename} className="truncate text-xs text-zinc-600 dark:text-zinc-300">
              {f.filename} <span className="text-zinc-400">({Math.round(f.size_bytes / 1024)} KB)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function MediaPanel({ projectId }: { projectId: string }) {
  const [manifest, setManifest] = useState<ImportedMediaManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    getProjectMedia(projectId)
      .then(setManifest)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load media"));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleUpload = async () => {
    const files = fileInputRef.current?.files;
    if (!files || files.length === 0) return;

    setIsUploading(true);
    setError(null);
    try {
      // One file per call still matches the backend's design (W3) - batched
      // client-side, not a bulk endpoint - but concurrently, not one at a
      // time: awaiting each upload before starting the next made total wait
      // time the SUM of every file's round trip instead of the slowest one,
      // which is what made multi-photo uploads feel so slow. Each file is
      // also compressed/renamed client-side (prepareForUpload) before it's
      // sent - the actual dominant cost for large source images.
      const results = await Promise.allSettled(
        Array.from(files).map(async (file) => uploadMedia(projectId, await prepareForUpload(file))),
      );
      const failures = results.filter((r): r is PromiseRejectedResult => r.status === "rejected");
      if (failures.length > 0) {
        const messages = failures.map((f) => (f.reason instanceof Error ? f.reason.message : String(f.reason)));
        setError(`${failures.length} of ${files.length} file(s) failed to upload: ${messages.join("; ")}`);
      } else if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } finally {
      setIsUploading(false);
      load();
    }
  };

  return (
    <Card>
      <CardTitle>Media</CardTitle>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {manifest && (
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <FileList label="Images" files={manifest.images} />
          <FileList label="Videos" files={manifest.videos} />
          <FileList label="Audio" files={manifest.audio} />
        </div>
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
      </div>
    </Card>
  );
}

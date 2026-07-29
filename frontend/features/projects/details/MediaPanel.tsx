"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getProjectMedia, uploadMedia } from "@/api/projects";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import type { ImportedMediaManifest } from "@/types/media";

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
      // One file per call, exactly matching the backend's design (W3) -
      // batch multiple files client-side, not by inventing a bulk endpoint.
      for (const file of Array.from(files)) {
        await uploadMedia(projectId, file);
      }
      if (fileInputRef.current) fileInputRef.current.value = "";
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
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

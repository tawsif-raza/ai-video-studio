"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { createProject } from "@/api/projects";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";

/**
 * POST /projects (W2) both creates the project AND starts a Director
 * Studio run in one call - there is no separate "create project" endpoint,
 * so this form is the only way to start Director Studio from the
 * dashboard. On success we route straight to the new project's detail
 * page with the run_id in the query string, so its Live Status panel can
 * pick up the in-flight run immediately.
 */
export function NewProjectForm({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [durationSeconds, setDurationSeconds] = useState(150);
  const [tone, setTone] = useState("");
  const [audience, setAudience] = useState("");
  const [artStyle, setArtStyle] = useState("");
  const [skipResearch, setSkipResearch] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await createProject({
        idea,
        duration_seconds: durationSeconds,
        tone: tone || null,
        audience: audience || null,
        art_style: artStyle || null,
        skip_research: skipResearch,
      });
      router.push(`/projects/${result.project_id}?runId=${result.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>New Project - Run Director Studio</CardTitle>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
        >
          Cancel
        </button>
      </div>
      <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">Idea *</span>
          <textarea
            required
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            rows={2}
            className="rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
            placeholder="A lighthouse keeper discovers a message in a bottle"
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">Duration (seconds)</span>
            <input
              type="number"
              min={10}
              value={durationSeconds}
              onChange={(e) => setDurationSeconds(Number(e.target.value))}
              className="rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">Tone</span>
            <input
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
              placeholder="uplifting"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">Audience</span>
            <input
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              className="rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">Art style</span>
            <input
              value={artStyle}
              onChange={(e) => setArtStyle(e.target.value)}
              className="rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-800"
              placeholder="3D animated, Pixar-style"
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={skipResearch}
            onChange={(e) => setSkipResearch(e.target.checked)}
            className="rounded border-zinc-300 dark:border-zinc-700"
          />
          Skip research stage
        </label>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <Button type="submit" isLoading={isSubmitting} disabled={!idea.trim()}>
          Run Director Studio
        </Button>
      </form>
    </Card>
  );
}

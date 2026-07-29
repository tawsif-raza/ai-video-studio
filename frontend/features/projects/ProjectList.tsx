"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { useProjects } from "@/hooks/useProjects";

import { NewProjectForm } from "./NewProjectForm";
import { ProjectCard } from "./ProjectCard";

export function ProjectList() {
  const { projects, isLoading, error, refetch } = useProjects();
  const searchParams = useSearchParams();
  const [showForm, setShowForm] = useState(searchParams.get("new") === "1");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {isLoading ? "Loading…" : `${projects.length} project${projects.length === 1 ? "" : "s"}`}
        </p>
        {!showForm && <Button onClick={() => setShowForm(true)}>New Project</Button>}
      </div>

      {showForm && (
        <NewProjectForm
          onClose={() => {
            setShowForm(false);
            refetch();
          }}
        />
      )}

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Failed to load projects: {error}
        </p>
      )}

      {!isLoading && !error && projects.length === 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No projects yet. Click &ldquo;New Project&rdquo; to run Director Studio and create one.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((project) => (
          <ProjectCard key={project.project_id} project={project} />
        ))}
      </div>
    </div>
  );
}

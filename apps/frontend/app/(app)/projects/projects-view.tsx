"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/button";
import { NewProjectModal } from "@/components/new-project-modal";
import { NewProjectCard, ProjectCard } from "@/components/project-card";
import { apiErrorMessage, listProjects, type ProjectList } from "@/lib/api";

export function ProjectsView() {
  // undefined: 불러오는 중
  const [list, setList] = useState<ProjectList>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listProjects().then(
      (list) => !cancelled && setList(list),
      (e) => !cancelled && setError(apiErrorMessage(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  function retry() {
    setError("");
    setAttempt((value) => value + 1);
  }

  if (error) {
    return (
      <div role="alert" className="flex items-center justify-between gap-4 rounded-control bg-danger-soft px-4 py-3">
        <p className="text-body text-danger">{error}</p>
        <Button variant="danger" className="bg-surface" onClick={retry}>
          다시 시도
        </Button>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-4 gap-4" aria-busy={!list}>
        {list
          ? list.items.map((project) => <ProjectCard key={project.id} project={project} />)
          : Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="h-[236px] animate-pulse rounded-card bg-[#eef0f4]" />
            ))}
        {list && <NewProjectCard onClick={() => setCreating(true)} />}
      </div>
      {creating && list && (
        <NewProjectModal nextColor={list.next_color} onClose={() => setCreating(false)} />
      )}
    </>
  );
}

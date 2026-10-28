import type { Metadata } from "next";
import { ProjectsView } from "./projects-view";

export const metadata: Metadata = { title: "프로젝트 · Feynmi" };

// 홈과 같은 이유로 instant 검증을 끈다 (app/(app)/page.tsx)
export const instant = false;

// design-system 9.9 프로젝트 목록
export default function ProjectsPage() {
  return (
    <div className="flex flex-col gap-7">
      <h1 className="text-title-1 font-bold text-text">프로젝트</h1>
      <ProjectsView />
    </div>
  );
}

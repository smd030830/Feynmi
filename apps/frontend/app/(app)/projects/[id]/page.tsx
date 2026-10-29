import type { Metadata } from "next";
import { Suspense } from "react";
import { ProjectDetailView } from "./project-detail-view";

export const metadata: Metadata = { title: "프로젝트 · Feynmi" };

// 홈과 같은 이유로 instant 검증을 끈다 (app/(app)/page.tsx)
export const instant = false;

// design-system 9.10 프로젝트 상세. 경로 id와 ?tab=은 요청 때 정해지므로
// 이를 읽는 클라이언트 컴포넌트를 Suspense로 감싼다 (cacheComponents).
export default function ProjectDetailPage() {
  return (
    <Suspense>
      <ProjectDetailView />
    </Suspense>
  );
}

"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Button, buttonStyles } from "@/components/button";
import { Icon, type IconName } from "@/components/icon";
import { ProgressRing } from "@/components/progress-ring";
import { ProjectTile } from "@/components/project-tile";
import { StateDistributionBar } from "@/components/state-distribution-bar";
import { ApiError, apiErrorMessage, getProject, type Project } from "@/lib/api";

const tabs = [
  { key: "concepts", label: "개념" },
  { key: "materials", label: "학습자료" },
  { key: "records", label: "학습기록" },
] as const;

type TabKey = (typeof tabs)[number]["key"];

function tabCount(project: Project, tab: TabKey) {
  if (tab === "concepts") return Object.values(project.state_counts).reduce((a, b) => a + b, 0);
  if (tab === "materials") return project.material_count;
  return 0; // 학습기록 수는 FM-044에서 채운다
}

export function ProjectDetailView() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: TabKey = tabs.some((t) => t.key === tabParam) ? (tabParam as TabKey) : "concepts";

  // undefined: 불러오는 중
  const [loaded, setLoaded] = useState<{ id: string; project?: Project; error?: unknown }>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getProject(id).then(
      (project) => !cancelled && setLoaded({ id, project }),
      (error) => !cancelled && setLoaded({ id, error }),
    );
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const current = loaded?.id === id ? loaded : undefined;

  if (current?.error) {
    const notFound = current.error instanceof ApiError && current.error.code === "not_found";
    return (
      <EmptyState
        icon="folder"
        title={notFound ? "프로젝트를 찾을 수 없어요" : "프로젝트를 불러오지 못했어요"}
        description={notFound ? "삭제되었거나 접근할 수 없는 프로젝트예요." : apiErrorMessage(current.error)}
      >
        {notFound ? (
          <Link href="/projects" className={buttonStyles("primary", "mt-5")}>
            프로젝트 목록으로
          </Link>
        ) : (
          <Button
            className="mt-5"
            onClick={() => {
              setLoaded(undefined);
              setAttempt((value) => value + 1);
            }}
          >
            다시 시도
          </Button>
        )}
      </EmptyState>
    );
  }

  const project = current?.project;
  if (!project) {
    return <div aria-busy className="h-[188px] animate-pulse rounded-card bg-[#eef0f4]" />;
  }

  return (
    <div className="flex flex-col gap-7">
      <nav aria-label="브레드크럼" className="flex items-center gap-1.5 text-caption text-subtle">
        <Link href="/projects" className="font-semibold hover:text-primary-strong">
          프로젝트
        </Link>
        <Icon name="chevron" size={14} className="text-placeholder" />
        <span aria-current="page" className="truncate font-semibold text-muted">
          {project.name}
        </span>
      </nav>

      <header className="flex items-center gap-6 rounded-card border border-line bg-surface p-7">
        <ProjectTile name={project.name} color={project.color} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="text-eyebrow font-extrabold uppercase text-primary-strong">
            Project · 자료 {project.material_count}개
          </p>
          <h1 className="mt-1 truncate text-title-1 font-bold text-text">{project.name}</h1>
          {project.description && (
            <p className="mt-0.5 whitespace-pre-line text-body-lg text-muted">{project.description}</p>
          )}
          <div className="mt-4 max-w-[420px]">
            <StateDistributionBar counts={project.state_counts} />
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-center gap-4">
          <ProgressRing score={project.score} />
          {/* 취약 개념 1순위로 새 세션 (FM-030). 개념이 없으면 비활성 */}
          <Button disabled>학습 시작하기</Button>
        </div>
      </header>

      <div>
        <div role="tablist" aria-label="프로젝트 탭" className="flex gap-[25px] border-b border-line">
          {tabs.map((t) => {
            const active = t.key === tab;
            return (
              <Link
                key={t.key}
                href={`/projects/${project.id}?tab=${t.key}`}
                replace
                scroll={false}
                role="tab"
                aria-selected={active}
                className={`-mb-px flex items-center gap-2 border-b-2 pb-3 text-body font-bold transition duration-200 ${
                  active
                    ? "border-primary text-primary-strong"
                    : "border-transparent text-subtle hover:text-text"
                }`}
              >
                {t.label}
                <span
                  className={`flex h-5 min-w-[22px] items-center justify-center rounded-full px-1.5 text-micro font-bold ${
                    active ? "bg-primary-soft text-primary-strong" : "bg-[#f1f5f9] text-subtle"
                  }`}
                >
                  {tabCount(project, t.key)}
                </span>
              </Link>
            );
          })}
        </div>

        <div role="tabpanel" className="pt-6">
          {tab === "concepts" && (
            <EmptyState
              icon="book"
              title="아직 개념이 없어요"
              description="학습자료를 올리면 핵심 개념을 뽑아 드려요."
            >
              <Link
                href={`/projects/${project.id}?tab=materials`}
                replace
                scroll={false}
                className={buttonStyles("primary", "mt-5")}
              >
                학습자료 올리러 가기
              </Link>
            </EmptyState>
          )}
          {tab === "materials" && (
            <section aria-labelledby="materials-title" className="flex flex-col gap-4">
              <div className="flex items-end justify-between">
                <div>
                  <h2 id="materials-title" className="text-heading font-bold text-text">
                    학습자료
                  </h2>
                  <p className="text-caption text-subtle">
                    PDF · PPTX 자료를 올리면 개념을 분석해 학습을 시작할 수 있어요.
                  </p>
                </div>
                {/* 업로드는 FM-020에서 연결한다 */}
                <Button disabled>학습자료 업로드</Button>
              </div>
              <EmptyState
                icon="file"
                title="아직 올린 자료가 없어요"
                description="PDF · PPTX, 파일당 50MB, 300쪽/슬라이드까지 올릴 수 있어요."
              />
              <p className="flex items-center gap-2 text-caption text-subtle">
                <Icon name="shield" size={16} className="text-placeholder" />
                업로드한 자료는 {project.name} 프로젝트의 개념 분석과 질문 생성에만 사용됩니다.
              </p>
            </section>
          )}
          {tab === "records" && (
            <EmptyState
              icon="chart"
              title="아직 학습기록이 없어요"
              description="개념을 설명하고 나면 여기에서 다시 볼 수 있어요."
            />
          )}
        </div>
      </div>
    </div>
  );
}

// design-system 8.2 Empty state
function EmptyState({
  icon,
  title,
  description,
  children,
}: {
  icon: IconName;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <section className="flex flex-col items-center rounded-card border border-line bg-surface px-6 py-14 text-center">
      <span className="flex size-[46px] items-center justify-center rounded-[13px] bg-primary-soft text-primary">
        <Icon name={icon} size={22} />
      </span>
      <h2 className="mt-4 text-subheading font-bold text-text">{title}</h2>
      <p className="mt-1 text-caption text-subtle">{description}</p>
      {children}
    </section>
  );
}

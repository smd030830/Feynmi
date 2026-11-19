"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/button";
import { Icon, type IconName } from "@/components/icon";
import { LearningOverview } from "@/components/learning-overview";
import { StateBadge } from "@/components/learning-feedback";
import { NewProjectModal } from "@/components/new-project-modal";
import { NewProjectCard, ProjectCard } from "@/components/project-card";
import { ProjectTile } from "@/components/project-tile";
import { apiErrorMessage, getHome, type HomeData } from "@/lib/api";
import { useStartLearning } from "@/lib/use-start-learning";

const cycle: { icon: IconName; label: string; tone: string }[] = [
  { icon: "book", label: "개념", tone: "bg-primary-soft text-primary" },
  { icon: "spark", label: "AI 질문", tone: "bg-[#ecfeff] text-[#0891b2]" },
  { icon: "target", label: "이해 분석", tone: "bg-success-soft text-success" },
];

export function HomeDashboard() {
  const [home, setHome] = useState<HomeData>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);
  const { begin, starting, startError } = useStartLearning();

  useEffect(() => {
    let active = true;
    getHome().then(
      (value) => { if (active) { setHome(value); setError(""); } },
      (reason) => { if (active) setError(apiErrorMessage(reason)); },
    );
    return () => { active = false; };
  }, [attempt]);

  if (error) return (
    <div role="alert" className="flex items-center justify-between gap-4 rounded-control bg-danger-soft p-4">
      <p className="text-body text-danger">{error}</p>
      <Button variant="soft" onClick={() => { setError(""); setAttempt((value) => value + 1); }}>다시 시도</Button>
    </div>
  );
  if (!home) return <p role="status" aria-busy className="text-body text-subtle">학습 현황을 불러오고 있어요…</p>;

  const recommendation = home.recommendation;
  const color = home.projects.find((project) => project.id === recommendation?.project_id)?.color ?? "indigo";

  return (
    <>
      {home.notifications.length > 0 && (
        <section aria-label="학습 알림" className="space-y-3">
          {home.notifications.map((notification) => (
            <div key={notification.kind} className="flex items-center gap-4 rounded-card border border-primary-line bg-primary-soft px-5 py-4 max-[600px]:flex-wrap max-[600px]:gap-3 max-[600px]:px-4">
              <Icon name="bell" size={20} className="shrink-0 text-primary" />
              <p className="flex-1 text-body font-semibold text-primary-strong">{notification.message}</p>
              {notification.kind === "review" && notification.concept_id && (
                <Button variant="soft" disabled={starting} onClick={() => notification.concept_id && void begin(notification.concept_id)}>복습하기</Button>
              )}
            </div>
          ))}
        </section>
      )}
      <section className="relative flex items-center justify-between overflow-hidden rounded-hero border border-primary-line bg-[linear-gradient(125deg,#eef2ff_0%,#f4f1ff_53%,#effaff_100%)] px-12 py-[38px] max-[600px]:flex-col max-[600px]:items-start max-[600px]:gap-6 max-[600px]:px-5 max-[600px]:py-7">
        <div className="absolute -right-16 -top-20 size-64 rounded-full bg-white/50" aria-hidden />
        <div className="relative">
          <p className="text-eyebrow font-extrabold uppercase text-primary-strong">Feynman Learning</p>
          <h2 className="mt-3 text-title-2 font-bold text-text">내 말로 설명하면,<br />이해한 만큼 보여요.</h2>
          {recommendation ? (
            <Button className="mt-6" disabled={starting} onClick={() => void begin(recommendation.concept_id)}>{starting ? "학습 준비 중…" : "지금 학습하기"}</Button>
          ) : <Button className="mt-6" onClick={() => setCreating(true)}>새 프로젝트 만들기</Button>}
        </div>
        <ol className="relative mr-6 flex items-center gap-3 max-[600px]:mr-0 max-[600px]:w-full max-[600px]:justify-between max-[600px]:gap-1" aria-label="학습 순환">
          {cycle.map((step, index) => (
            <li key={step.label} className="flex items-center gap-3">
              <div className="flex flex-col items-center gap-2">
                <span className={`flex size-14 items-center justify-center rounded-2xl shadow-brand-sm max-[600px]:size-11 ${step.tone}`}><Icon name={step.icon} size={24} /></span>
                <span className="text-micro font-bold text-muted">{step.label}</span>
              </div>
              {index < cycle.length - 1 && <Icon name="arrow" size={16} className="mb-6 text-placeholder" />}
            </li>
          ))}
        </ol>
      </section>

      {startError && <p role="alert" className="rounded-control bg-danger-soft p-4 text-body text-danger">{startError}</p>}

      {home.projects.length === 0 ? (
        <section className="flex flex-col items-center rounded-card border border-line bg-surface px-6 py-14 text-center">
          <Icon name="folder" size={28} className="text-primary" />
          <h2 className="mt-4 text-subheading font-bold text-text">첫 프로젝트를 만들어보세요</h2>
          <p className="mt-1 text-caption text-subtle">학습자료를 올리면 핵심 개념을 뽑아 드려요.</p>
          <Button className="mt-5" onClick={() => setCreating(true)}>새 프로젝트</Button>
        </section>
      ) : (
        <>
          <LearningOverview stats={home.stats} />
          {recommendation && (
            <section aria-labelledby="recommendation-title" className="flex items-center gap-5 rounded-card border border-primary-line bg-surface p-6 max-[600px]:flex-col max-[600px]:items-start max-[600px]:gap-3 max-[600px]:p-4">
              <ProjectTile name={recommendation.concept_title} color={color} size="lg" />
              <div className="min-w-0 flex-1">
                <p id="recommendation-title" className="text-caption font-bold text-primary-strong">다음 학습 추천</p>
                <h2 className="mt-1 truncate text-title-3 font-bold text-text">{recommendation.concept_title}</h2>
                <p className="mt-1 text-caption text-subtle">{recommendation.project_name} · {recommendation.reason}</p>
                <div className="mt-3 flex items-center gap-3">
                  <StateBadge state={recommendation.state} score={recommendation.score} />
                  <span className="text-body font-bold text-muted">{recommendation.score === null ? "-" : `${recommendation.score}%`}</span>
                </div>
                <div role="progressbar" aria-label="추천 개념 이해도" aria-valuenow={recommendation.score ?? 0} aria-valuemin={0} aria-valuemax={100} className="mt-3 h-1.5 w-full max-w-80 overflow-hidden rounded-full bg-canvas">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${recommendation.score ?? 0}%` }} />
                </div>
              </div>
              <Button disabled={starting} onClick={() => void begin(recommendation.concept_id)}>학습하기</Button>
            </section>
          )}
          <section aria-labelledby="projects-title">
            <div className="mb-4 flex items-baseline justify-between">
              <h2 id="projects-title" className="text-heading font-bold text-text">나의 프로젝트</h2>
              <Link href="/projects" className="text-caption font-semibold text-primary-strong">전체 보기</Link>
            </div>
            <div className="grid grid-cols-4 gap-4 max-[1024px]:grid-cols-2 max-[600px]:grid-cols-1">
              {home.projects.map((project) => <ProjectCard key={project.id} project={project} />)}
              <NewProjectCard onClick={() => setCreating(true)} />
            </div>
          </section>
        </>
      )}
      {creating && <NewProjectModal nextColor={home.next_color} onClose={() => setCreating(false)} />}
    </>
  );
}

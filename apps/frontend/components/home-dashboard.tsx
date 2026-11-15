"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/button";
import { Icon, type IconName } from "@/components/icon";
import { LearningOverview } from "@/components/learning-overview";
import { StateBadge } from "@/components/learning-feedback";
import { NewProjectModal } from "@/components/new-project-modal";
import { NewProjectCard, ProjectCard } from "@/components/project-card";
import { ProjectTile } from "@/components/project-tile";
import { apiErrorMessage, getHome, startSession, type HomeData } from "@/lib/api";

const cycle: { icon: IconName; label: string; tone: string }[] = [
  { icon: "book", label: "개념", tone: "bg-primary-soft text-primary" },
  { icon: "spark", label: "AI 질문", tone: "bg-[#ecfeff] text-[#0891b2]" },
  { icon: "target", label: "이해 분석", tone: "bg-success-soft text-success" },
];

export function HomeDashboard() {
  const router = useRouter();
  const [home, setHome] = useState<HomeData>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [creating, setCreating] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const pending = useRef(false);

  useEffect(() => {
    let active = true;
    getHome().then(
      (value) => { if (active) { setHome(value); setError(""); } },
      (reason) => { if (active) setError(apiErrorMessage(reason)); },
    );
    return () => { active = false; };
  }, [attempt]);

  async function begin(conceptId: string) {
    if (pending.current) return;
    pending.current = true;
    setStarting(true);
    setStartError("");
    try {
      const session = await startSession(conceptId);
      router.push(`/sessions/${session.id}`);
    } catch (reason) {
      setStartError(apiErrorMessage(reason));
      pending.current = false;
      setStarting(false);
    }
  }

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
      <section className="relative flex items-center justify-between overflow-hidden rounded-hero border border-primary-line bg-[linear-gradient(125deg,#eef2ff_0%,#f4f1ff_53%,#effaff_100%)] px-12 py-[38px]">
        <div className="absolute -right-16 -top-20 size-64 rounded-full bg-white/50" aria-hidden />
        <div className="relative">
          <p className="text-eyebrow font-extrabold uppercase text-primary-strong">Feynman Learning</p>
          <h2 className="mt-3 text-title-2 font-bold text-text">내 말로 설명하면,<br />이해한 만큼 보여요.</h2>
          {recommendation ? (
            <Button className="mt-6" disabled={starting} onClick={() => void begin(recommendation.concept_id)}>{starting ? "학습 준비 중…" : "지금 학습하기"}</Button>
          ) : <Button className="mt-6" onClick={() => setCreating(true)}>새 프로젝트 만들기</Button>}
        </div>
        <ol className="relative mr-6 flex items-center gap-3" aria-label="학습 순환">
          {cycle.map((step, index) => (
            <li key={step.label} className="flex items-center gap-3">
              <div className="flex flex-col items-center gap-2">
                <span className={`flex size-14 items-center justify-center rounded-2xl shadow-brand-sm ${step.tone}`}><Icon name={step.icon} size={24} /></span>
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
            <section aria-labelledby="recommendation-title" className="flex items-center gap-5 rounded-card border border-primary-line bg-surface p-6">
              <ProjectTile name={recommendation.concept_title} color={color} size="lg" />
              <div className="min-w-0 flex-1">
                <p id="recommendation-title" className="text-caption font-bold text-primary-strong">다음 학습 추천</p>
                <h2 className="mt-1 truncate text-title-3 font-bold text-text">{recommendation.concept_title}</h2>
                <p className="mt-1 text-caption text-subtle">{recommendation.project_name} · {recommendation.reason}</p>
                <div className="mt-3 flex items-center gap-3">
                  <StateBadge state={recommendation.state} />
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
            <div className="grid grid-cols-4 gap-4">
              {home.projects.map((project) => <ProjectCard key={project.id} project={project} />)}
              <NewProjectCard onClick={() => setCreating(true)} />
            </div>
          </section>
          <section aria-labelledby="weak-title">
            <h2 id="weak-title" className="mb-4 text-heading font-bold text-text">취약 개념</h2>
            {home.weak_concepts.length === 0 ? (
              <div className="rounded-card border border-line bg-surface p-8 text-center">
                <p className="text-subheading font-bold text-text">
                  {home.projects.some((project) => Object.values(project.state_counts).some((count) => count > 0)) ? "모든 개념을 이해했어요" : "아직 학습할 개념이 없어요"}
                </p>
                <p className="mt-2 text-caption text-subtle">새로운 학습자료를 올려 다음 개념을 만나보세요.</p>
              </div>
            ) : (
              <ul className="overflow-hidden rounded-card border border-line bg-surface divide-y divide-line">
                {home.weak_concepts.map((concept) => (
                  <li key={concept.concept_id}>
                    <button type="button" disabled={starting} onClick={() => void begin(concept.concept_id)} className="flex w-full items-center gap-5 p-5 text-left transition hover:bg-primary-soft disabled:opacity-60">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-subheading font-bold text-text">{concept.concept_title}</span>
                        <span className="mt-1 block truncate text-caption text-subtle">{concept.project_name}</span>
                      </span>
                      <StateBadge state={concept.state} />
                      <span className="min-w-12 text-right text-body font-bold text-muted">{concept.score === null ? "-" : `${concept.score}%`}</span>
                      <Icon name="chevron" size={18} className="shrink-0 text-placeholder" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
      {creating && <NewProjectModal nextColor={home.next_color} onClose={() => setCreating(false)} />}
    </>
  );
}

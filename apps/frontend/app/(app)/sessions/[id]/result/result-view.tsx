"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, buttonStyles } from "@/components/button";
import { Conversation, FeedbackList, StateBadge } from "@/components/learning-feedback";
import { ProgressRing } from "@/components/progress-ring";
import { apiErrorMessage, getSessionResult, startSession, type LearningSession } from "@/lib/api";

export function ResultView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [loaded, setLoaded] = useState<{ id: string; session?: LearningSession; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    getSessionResult(id).then((session) => !cancelled && setLoaded({ id, session }), (err) => !cancelled && setLoaded({ id, error: apiErrorMessage(err) }));
    return () => { cancelled = true; };
  }, [id, attempt]);
  const session = loaded?.id === id ? loaded.session : undefined;
  async function next() {
    if (!session?.recommendation) return;
    setPending(true); setError("");
    try { const value = await startSession(session.recommendation.concept_id); setPending(false); router.push(`/sessions/${value.id}`); }
    catch (err) { setError(apiErrorMessage(err)); setPending(false); }
  }
  if (loaded?.id === id && loaded.error) return <div role="alert" className="rounded-card border border-line bg-surface p-8"><p>{loaded.error}</p><Button className="mt-4" onClick={() => setAttempt((n) => n + 1)}>다시 시도</Button><Link href={`/sessions/${id}`} className={buttonStyles("ghost", "ml-2")}>학습 상세로</Link></div>;
  if (!session) return <p aria-busy className="text-body text-subtle">학습 결과를 불러오고 있어요…</p>;
  const final = session.assessments.at(-1);
  const first = session.assessments[0];
  const difference = session.score_change ?? 0;
  const duration = Math.max(1, Math.ceil((Date.parse(session.ended_at ?? session.started_at) - Date.parse(session.started_at)) / 60000));
  const coreCount = final?.elements.filter((e) => e.importance === "core").length ?? 0;
  const feedback = final?.feedback;
  return <div className="space-y-7">
    <Link href={`/projects/${session.project_id}`} className="text-caption font-semibold text-subtle">{session.project_name} › {session.concept_title}</Link>
    <header className="flex items-end justify-between"><div><p className="text-eyebrow font-bold text-primary-strong">LEARNING COMPLETE</p><h1 className="mt-2 text-title-1 font-bold">학습 결과</h1><p className="mt-1 text-body-lg text-muted">설명 속에 드러난 이해를 분석했어요.</p></div><p className="text-caption text-subtle">{new Date(session.started_at).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" })} · {duration}분 학습</p></header>
    <section className="grid grid-cols-[1fr_auto_1fr] items-center gap-9 rounded-hero border border-primary-line bg-surface p-8">
      <div><p className="text-caption font-bold text-subtle">학습 개념</p><h2 className="mt-2 text-title-2 font-bold">{session.concept_title}</h2><div className="mt-3"><FeedbackList items={feedback?.summary_points ?? []} /></div><p className="mt-5 text-body font-bold text-primary-strong">{difference > 0 ? `+${difference}%p 상승` : difference < 0 ? `${Math.abs(difference)}%p 하락` : "변화 없음"}</p><p className="text-caption text-subtle">{first?.score ?? 0}%에서 시작했어요</p></div>
      <ProgressRing score={final?.score ?? null} />
      <div><p className="mb-3 text-caption font-bold text-subtle">현재 단계</p><StateBadge state={final?.state ?? "not_studied"} /><p className="mt-4 text-body font-bold text-muted">{session.remaining_core_count === 0 ? "모든 핵심 요소를 충족했어요" : `이해까지 남은 핵심 요소 ${session.remaining_core_count ?? 0}개`}</p><progress aria-label="충족한 핵심 요소" className="mt-3 h-2 w-full accent-primary" max={coreCount || 1} value={coreCount - (session.remaining_core_count ?? 0)} /></div>
    </section>
    <section className="grid grid-cols-3 gap-4" aria-label="설명 분석">{[
      { title: "잘 이해한 부분", items: feedback?.correct ?? [], color: "text-success", bg: "bg-success-soft" },
      { title: "보완이 필요한 부분", items: feedback?.missing ?? [], color: "text-warning", bg: "bg-warning-soft" },
      { title: "잘못 이해한 부분", items: feedback?.incorrect ?? [], color: "text-danger", bg: "bg-danger-soft" },
    ].map((part) => <div key={part.title} className={`rounded-card border border-line p-5 ${part.bg}`}><h2 className={`mb-4 text-subheading font-bold ${part.color}`}>{part.title}</h2><FeedbackList items={part.items} /></div>)}</section>
    <section className="rounded-card border border-line bg-surface p-6"><h2 className="text-heading font-bold">AI 분석 요약</h2><p className="mt-4 whitespace-pre-wrap text-body-lg text-muted">{feedback?.supplement || "추가 보완 설명이 없어요."}</p>{!!feedback?.unverified_statements?.length && <div className="mt-5 rounded-control bg-primary-soft p-4"><h3 className="text-body font-bold text-primary-strong">자료에서 확인되지 않음</h3>{feedback.unverified_statements.map((item, i) => <p key={i} className="mt-2 text-body text-muted">“{item.learner_quote}” · {item.note}</p>)}</div>}</section>
    {session.recommendation && <section className="flex items-center justify-between gap-6 rounded-card border border-primary-line bg-primary-soft p-6"><div><p className="text-caption font-bold text-primary-strong">다음 학습 추천 · {session.recommendation.reason}</p><h2 className="mt-2 text-title-3 font-bold">{session.recommendation.concept_title}</h2><p className="mt-1 text-caption text-subtle">{session.recommendation.project_name} · {session.recommendation.score === null ? "미학습" : `${session.recommendation.score}%`}</p><div className="mt-2"><StateBadge state={session.recommendation.state} /></div></div><Button disabled={pending} onClick={next}>다음 학습 시작하기</Button></section>}
    {error && <p role="alert" className="text-body text-danger">{error}</p>}
    <div className="flex items-center justify-between"><Link href={`/projects/${session.project_id}`} className={buttonStyles("ghost")}>프로젝트로 돌아가기</Link><span role="status" className="rounded-control bg-success-soft px-4 py-3 text-body font-bold text-success">학습 결과 저장됨 ✓</span></div>
    <details className="rounded-card border border-line bg-surface p-6"><summary className="cursor-pointer text-subheading font-bold">대화 다시 보기</summary><div className="mt-6"><Conversation messages={session.messages} assessments={session.assessments} /></div></details>
  </div>;
}

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, buttonStyles } from "@/components/button";
import { Conversation, FeedbackList, StateBadge } from "@/components/learning-feedback";
import { MisconceptionReview } from "@/components/misconception-review";
import { AssessmentEvidence } from "@/components/assessment-evidence";
import { ProgressRing } from "@/components/progress-ring";
import { apiErrorMessage, getSessionResult, type LearningSession } from "@/lib/api";
import { useStartLearning } from "@/lib/use-start-learning";

export function ResultView() {
  const { id } = useParams<{ id: string }>();
  const [loaded, setLoaded] = useState<{ id: string; session?: LearningSession; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  const { begin, starting, startError } = useStartLearning();
  useEffect(() => {
    let cancelled = false;
    getSessionResult(id).then((session) => !cancelled && setLoaded({ id, session }), (err) => !cancelled && setLoaded({ id, error: apiErrorMessage(err) }));
    return () => { cancelled = true; };
  }, [id, attempt]);
  const session = loaded?.id === id ? loaded.session : undefined;
  async function next() {
    if (session?.recommendation) await begin(session.recommendation.concept_id);
  }
  if (loaded?.id === id && loaded.error) return <div role="alert" className="rounded-card border border-line bg-surface p-8"><p>{loaded.error}</p><Button className="mt-4" onClick={() => setAttempt((n) => n + 1)}>다시 시도</Button><Link href={`/sessions/${id}`} className={buttonStyles("ghost", "ml-2")}>학습 상세로</Link></div>;
  if (!session) return <p aria-busy className="text-body text-subtle">학습 결과를 불러오고 있어요…</p>;
  const final = session.assessments.at(-1);
  const first = session.assessments[0];
  const difference = session.score_change ?? 0;
  const duration = Math.max(1, Math.ceil((Date.parse(session.ended_at ?? session.started_at) - Date.parse(session.started_at)) / 60000));
  const coreCount = final?.elements.filter((e) => e.importance === "core").length ?? 0;
  const feedback = final?.feedback;
  const needsWork = final?.state === "partial" || final?.state === "misconception"
    || final?.elements.some((element) => element.verdict !== "met");
  const gaps = final?.elements.filter((element) => element.verdict !== "met") ?? [];
  const feedbackGroups = [
    { verdict: "missing", title: "빼먹은 내용", description: "답변에서 확인되지 않은 학습 항목이에요.", action: "설명에 추가할 내용", color: "text-warning" },
    { verdict: "contradicted", title: "오개념", description: "자료와 다르게 이해한 내용을 바로잡아보세요.", action: "바로잡아 설명할 내용", color: "text-danger" },
    { verdict: "partial", title: "설명이 부족한 부분", description: "언급했지만 조건이나 이유를 더 설명해야 하는 항목이에요.", action: "더 구체적으로 설명할 내용", color: "text-primary-strong" },
  ];
  return <div className="space-y-7">
    {session.project_available === false ? <p className="text-caption font-semibold text-subtle">{session.project_name} (삭제된 프로젝트) › {session.concept_title}</p> : <Link href={`/projects/${session.project_id}`} className="text-caption font-semibold text-subtle">{session.project_name} › {session.concept_title}</Link>}
    <header className="flex items-end justify-between"><div><p className="text-eyebrow font-bold text-primary-strong">LEARNING COMPLETE</p><h1 className="mt-2 text-title-1 font-bold">학습 결과</h1><p className="mt-1 text-body-lg text-muted">{session.end_reason === "max_followups" ? "질문 횟수에 도달했어요. 남은 부분을 확인하고 다시 학습해보세요." : "이해도 100%에 도달해 학습을 마쳤어요."}</p></div><p className="text-caption text-subtle">{new Date(session.started_at).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" })} · {duration}분 학습</p></header>
    {session.concept_available === false && <p className="rounded-control bg-canvas p-4 text-body text-muted">학습자료가 삭제되었어요. 당시 결과와 대화는 아래에서 볼 수 있어요.</p>}
    <section className="grid grid-cols-[1fr_auto_1fr] items-center gap-9 rounded-hero border border-primary-line bg-surface p-8">
      <div><p className="text-caption font-bold text-subtle">학습 개념</p><h2 className="mt-2 text-title-2 font-bold">{session.concept_title}</h2>{needsWork && !!feedback?.summary_points?.length && <div className="mt-3"><FeedbackList items={feedback.summary_points} /></div>}<p className="mt-5 text-body font-bold text-primary-strong">{difference > 0 ? `+${difference}%p 상승` : difference < 0 ? `${Math.abs(difference)}%p 하락` : "변화 없음"}</p><p className="text-caption text-subtle">{first?.score ?? 0}%에서 시작했어요</p></div>
      <ProgressRing score={final?.score ?? null} />
      <div><p className="mb-3 text-caption font-bold text-subtle">현재 단계</p><StateBadge state={final?.state ?? "not_studied"} /><p className="mt-4 text-body font-bold text-muted">{session.remaining_core_count === 0 ? "모든 핵심 요소를 충족했어요" : `이해까지 남은 핵심 요소 ${session.remaining_core_count ?? 0}개`}</p><progress aria-label="충족한 핵심 요소" className="mt-3 h-2 w-full accent-primary" max={coreCount || 1} value={coreCount - (session.remaining_core_count ?? 0)} /></div>
    </section>
    {needsWork ? <section aria-label="보완할 내용" className="space-y-4">
      <h2 className="text-heading font-bold">다음 설명에서 보완할 내용</h2>
      {feedbackGroups.map((group) => {
        const elements = gaps.filter((element) => element.verdict === group.verdict);
        if (elements.length === 0) return null;
        return <section key={group.verdict} aria-label={group.title} className="space-y-3">
          <div><h3 className={`text-subheading font-bold ${group.color}`}>{group.title} · {elements.length}개</h3><p className="mt-1 text-body text-muted">{group.description}</p></div>
          {elements.map((element) => <article key={element.element_id} className="rounded-card border border-line bg-surface p-6">
            <h4 className="text-subheading font-bold">{element.text}</h4>
            <p className="mt-4 text-caption font-bold text-subtle">내 답변</p>
            {element.learner_quote
              ? <blockquote className="mt-2 border-l-2 border-primary-line pl-3 text-body text-muted">“{element.learner_quote}”</blockquote>
              : <p className="mt-2 text-body text-muted">이 항목을 설명한 문장이 답변에서 확인되지 않았어요.</p>}
            <p className="mt-4 text-caption font-bold text-subtle">보완이 필요한 이유</p>
            <p className="mt-2 whitespace-pre-wrap text-body text-muted">{element.note?.trim() || (element.verdict === "missing" ? "이 항목에 대한 설명을 추가해야 이해 여부를 확인할 수 있어요." : element.verdict === "contradicted" ? "자료의 설명과 충돌하는 부분이 있어요. 아래 근거와 내 답변을 비교해보세요." : "설명한 내용만으로는 이 항목의 조건이나 적용 과정을 충분히 확인하기 어려워요.")}</p>
            <p className="mt-4 text-caption font-bold text-subtle">{group.action}</p>
            <p className="mt-2 text-body font-semibold text-primary-strong">{element.text}</p>
            {element.evidence.map((source) => <div key={source.id} className="mt-4 rounded-control bg-canvas p-4">
              <p className="text-caption font-bold">{source.material_title} · {source.page_start}{source.page_end !== source.page_start ? `–${source.page_end}` : ""}쪽/슬라이드</p>
              {source.text && <blockquote className="mt-2 whitespace-pre-wrap text-body text-muted">{source.text}</blockquote>}
            </div>)}
          </article>)}
        </section>;
      })}
      {gaps.length === 0 && <FeedbackList items={[...(feedback?.missing ?? []), ...(feedback?.incorrect ?? []), ...(feedback?.missing_hint ?? [])]} />}
    </section> : <p className="text-body text-subtle">추가로 보완할 부분이 없어요.</p>}
    {needsWork && !!feedback?.supplement?.trim() && <section className="rounded-card border border-line bg-surface p-6"><h2 className="text-heading font-bold">상세 풀이</h2><p className="mt-4 whitespace-pre-wrap text-body-lg text-muted">{feedback.supplement}</p></section>}
    <MisconceptionReview session={session} />
    <AssessmentEvidence assessments={session.assessments} />
    {!!feedback?.unverified_statements?.length && <section className="rounded-card border border-line bg-primary-soft p-6"><h2 className="text-heading font-bold text-primary-strong">자료에서 확인되지 않음</h2>{feedback.unverified_statements.map((item, i) => <p key={i} className="mt-2 text-body text-muted">“{item.learner_quote}” · {item.note}</p>)}</section>}
    {session.recommendation && <section className="flex items-center justify-between gap-6 rounded-card border border-primary-line bg-primary-soft p-6"><div><p className="text-caption font-bold text-primary-strong">다음 학습 추천 · {session.recommendation.reason}</p><h2 className="mt-2 text-title-3 font-bold">{session.recommendation.concept_title}</h2><p className="mt-1 text-caption text-subtle">{session.recommendation.project_name} · {session.recommendation.score === null ? "미학습" : `${session.recommendation.score}%`}</p><div className="mt-2"><StateBadge state={session.recommendation.state} /></div></div><Button disabled={starting} onClick={next}>다음 학습 시작하기</Button></section>}
    {startError && <p role="alert" className="text-body text-danger">{startError}</p>}
    <div className="flex items-center justify-between"><Link href={session.project_available === false ? "/records" : `/projects/${session.project_id}`} className={buttonStyles("ghost")}>{session.project_available === false ? "학습기록으로 돌아가기" : "프로젝트로 돌아가기"}</Link><span role="status" className="rounded-control bg-success-soft px-4 py-3 text-body font-bold text-success">학습 결과 저장됨 ✓</span></div>
    <details className="rounded-card border border-line bg-surface p-6"><summary className="cursor-pointer text-subheading font-bold">대화 다시 보기</summary><div className="mt-6"><Conversation messages={session.messages} assessments={session.assessments} /></div></details>
  </div>;
}

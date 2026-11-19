"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, buttonStyles } from "@/components/button";
import { confidenceLabels, Conversation, StateBadge } from "@/components/learning-feedback";
import { Modal } from "@/components/modal";
import { abortSession, abortSessionOnExit, apiErrorMessage, ApiError, getSession, submitAnswer, type AnswerConfidence, type LearningSession } from "@/lib/api";
import { getFirebaseAuth } from "@/lib/firebase";
import { useSpeechDictation } from "@/lib/use-speech-dictation";
import { useStartLearning } from "@/lib/use-start-learning";

const verdictLabels = { met: "충족", partial: "부분", missing: "누락", contradicted: "모순" };
const confidenceOptions = ["high", "uncertain", "low"] as const;

export function SessionView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const [loaded, setLoaded] = useState<{ id: string; session?: LearningSession; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  const [answer, setAnswer] = useState("");
  const [confidenceDraft, setConfidenceDraft] = useState<{ id: string; value: AnswerConfidence }>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [answerError, setAnswerError] = useState("");
  const [confirmExit, setConfirmExit] = useState(false);
  const { begin, starting, startError } = useStartLearning();
  const { state: speechState, message: speechMessage, start: startSpeech, stop: stopSpeech, abort: abortSpeech, isActive: speechIsActive } =
    useSpeechDictation(id, (text) => setAnswer((draft) => draft && !/\s$/.test(draft) ? `${draft} ${text}` : draft + text));
  const live = useRef<{ session?: LearningSession; pending: boolean; token: string }>({ pending: false, token: "" });
  const session = loaded?.id === id ? loaded.session : undefined;

  useEffect(() => {
    let cancelled = false;
    const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    // navigation 항목은 이후 SPA 이동에도 유지되므로 새로고침한 문서의 세션에만 적용한다.
    const reload = navigation?.type === "reload" && new URL(navigation.name).pathname === `/sessions/${encodeURIComponent(id)}`;
    (async () => {
      const value = reload ? await abortSession(id) : await getSession(id);
      if (!cancelled) {
        live.current.session = value;
        live.current.pending = false;
        setPending(false);
        setLoaded({ id, session: value });
      }
    })().catch((err) => !cancelled && setLoaded({ id, error: apiErrorMessage(err) }));
    return () => { cancelled = true; };
  }, [id, attempt]);

  useEffect(() => {
    live.current.session = session;
    if (session?.status === "completed") router.replace(`/sessions/${id}/result`);
  }, [session, id, router]);

  useEffect(() => {
    let active = true;
    const refreshToken = () => void getFirebaseAuth().currentUser?.getIdToken().then((token) => { if (active) live.current.token = token; }).catch(() => {});
    refreshToken();
    const timer = window.setInterval(refreshToken, 5 * 60 * 1000);
    const exit = () => {
      if (live.current.session?.id === id && live.current.session.status === "in_progress" && live.current.token) {
        void abortSessionOnExit(id, live.current.token).catch(() => {});
      }
    };
    const navigate = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest<HTMLAnchorElement>("a[href]");
      if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
      const url = new URL(link.href);
      if (url.origin !== location.origin || url.pathname === pathname || live.current.session?.status !== "in_progress") return;
      event.preventDefault();
      event.stopPropagation();
      if (live.current.pending) { setError("설명을 분석 중이에요. 분석이 끝나면 이동할 수 있어요."); return; }
      abortSpeech();
      live.current.pending = true;
      setPending(true);
      void abortSession(id).then((updated) => {
        live.current.session = updated;
        live.current.pending = false;
        setLoaded({ id, session: updated });
        setPending(false);
        router.push(url.pathname + url.search + url.hash);
      }).catch((err) => { live.current.pending = false; setError(apiErrorMessage(err)); setPending(false); });
    };
    window.addEventListener("pagehide", exit);
    window.addEventListener("popstate", exit);
    document.addEventListener("click", navigate, true);
    return () => {
      // 화면 이동으로 숨겨지는 경우에도 중단한다. StrictMode의 첫 마운트 정리는
      // 같은 URL에서 실행되므로 실제 학습을 중단하지 않는다.
      if (location.pathname !== pathname) exit();
      active = false;
      clearInterval(timer);
      window.removeEventListener("pagehide", exit);
      window.removeEventListener("popstate", exit);
      document.removeEventListener("click", navigate, true);
    };
  }, [abortSpeech, id, pathname, router]);

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (!answer.trim() || speechIsActive() || live.current.pending || session?.status !== "in_progress") return;
    live.current.pending = true;
    setPending(true); setError(""); setAnswerError("");
    try {
      const confidence = confidenceDraft?.id === id ? confidenceDraft.value : undefined;
      const updated = await submitAnswer(id, answer.trim(), confidence);
      setLoaded({ id, session: updated }); setAnswer(""); setConfidenceDraft(undefined);
    } catch (err) {
      if (err instanceof ApiError && ["off_topic_response", "answer_filter_unavailable"].includes(err.code)) {
        setAnswerError(apiErrorMessage(err));
      } else {
        setError(apiErrorMessage(err));
      }
      // 실패한 답변도 서버에 보관될 수 있으므로 대화를 다시 읽는다.
      try { setLoaded({ id, session: await getSession(id) }); } catch { /* 기존 대화와 입력을 유지한다. */ }
    } finally { live.current.pending = false; setPending(false); }
  }
  async function finish() {
    if (live.current.pending) return;
    abortSpeech();
    live.current.pending = true;
    setPending(true); setError("");
    try { const updated = await abortSession(id); live.current.session = updated; live.current.pending = false; setPending(false); setLoaded({ id, session: updated }); setConfirmExit(false); router.push(`/projects/${updated.project_id}`); }
    catch (err) { setError(apiErrorMessage(err)); } finally { live.current.pending = false; setPending(false); }
  }
  async function restart() {
    if (!session || session.concept_available === false || live.current.pending) return;
    setError("");
    await begin(session.concept_id);
  }

  if (loaded?.id === id && loaded.error) return <div role="alert" className="rounded-card border border-line bg-surface p-8"><p>{loaded.error}</p><Button className="mt-4" onClick={() => setAttempt((n) => n + 1)}>다시 시도</Button></div>;
  if (!session) return <p aria-busy className="text-body text-subtle">학습을 불러오고 있어요…</p>;
  const latest = session.assessments.at(-1);
  const currentQuestion = session.messages.findLast((message) => message.role === "question");
  const hintSource = session.hint_source;
  const ended = session.status !== "in_progress";
  const evidence = [...new Map(latest?.elements.flatMap((e) => e.evidence).map((e) => [e.id, e]) ?? []).values()];

  return <div className="space-y-7">
    <div className="flex items-center justify-between">{session.project_available === false ? <p className="text-caption font-semibold text-subtle">{session.project_name} (삭제된 프로젝트) › {session.concept_title}</p> : <Link href={`/projects/${session.project_id}`} className="text-caption font-semibold text-subtle">{session.project_name} › {session.concept_title}</Link>}{!ended && <Button variant="soft" disabled={pending} onClick={() => { stopSpeech(); setConfirmExit(true); }}>학습 종료</Button>}</div>
    <header className="flex items-end justify-between gap-4"><div><p className="text-eyebrow font-bold text-primary-strong">FEYNMAN 학습</p><h1 className="mt-2 text-title-1 font-bold">{session.concept_title}</h1></div><span className="shrink-0 text-caption text-subtle">{ended ? "중단된 학습" : "이해도 100%에서 완료"}</span></header>
    {session.concept_available === false && <p className="rounded-control bg-canvas p-4 text-body text-muted">학습자료가 삭제되어 이 개념을 다시 학습할 수 없어요. 당시 설명과 피드백은 아래에서 볼 수 있어요.</p>}
    {!ended && <p aria-live="polite" className="text-caption font-bold text-primary-strong">{session.followups_used > 0 ? `추가 질문 ${session.followups_used}` : "개념 설명"}</p>}
    {(error || startError) && <p role="alert" className="rounded-control bg-danger-soft p-4 text-body text-danger">{error || startError}</p>}
    <div className={ended ? "" : "grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_270px] lg:gap-6"}>
      <section className="min-w-0 space-y-6"><div className="flex justify-between"><h2 className="text-heading font-bold">{ended ? "중단된 학습의 대화" : "설명하며 이해하기"}</h2>{pending && <span role="status" className="text-caption text-primary-strong">대화 분석 중…</span>}</div>
        <Conversation messages={session.messages} assessments={session.assessments} />
        {!ended ? <form onSubmit={send} className="min-w-0 rounded-card border border-primary-line bg-surface p-4 shadow-brand sm:p-5">
          <p className="text-caption font-bold text-primary-strong">현재 질문</p><p className="mt-1 text-body text-muted">{currentQuestion?.text}</p>
          {currentQuestion && hintSource && (
            <details key={currentQuestion.id} className="mt-3 rounded-control border border-line bg-canvas p-3">
              <summary className="cursor-pointer text-caption font-bold text-primary-strong">힌트 보기</summary>
              <p className="mt-2 break-words text-caption text-muted">
                「{hintSource.material_title}」
                {hintSource.page_start != null && (
                  <> · {hintSource.page_start}{hintSource.page_end != null && hintSource.page_end !== hintSource.page_start ? `–${hintSource.page_end}` : ""}쪽/슬라이드</>
                )}에서 질문과 관련된 부분을 찾아보세요.
              </p>
              <details className="mt-2">
                <summary className="cursor-pointer text-caption font-semibold text-primary-strong">생각의 실마리 보기</summary>
                <p className="mt-2 text-caption text-muted">
                  {latest
                    ? "지금 질문에 해당하는 사례를 하나 골라보세요. 조건 하나가 달라지면 결과가 어떻게 바뀔까요? 그 이유를 설명해 보세요."
                    : "질문에서 설명하라고 한 대상이나 조건을 하나 골라보세요. 자료 속 사례에서 언제 나타나고 왜 그런지 한 문장씩 설명해 보세요."}
                </p>
              </details>
            </details>
          )}
          <label htmlFor="learner-answer" className="sr-only">나의 설명</label><textarea id="learner-answer" value={answer} onChange={(e) => { setAnswer(e.target.value); setAnswerError(""); }} disabled={pending} placeholder="내 말로 설명해보세요..." className={`mt-4 min-h-36 w-full resize-y rounded-control border p-4 text-body-lg disabled:opacity-60 ${
  answerError ? "border-danger" : "border-line"
}`} onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void send(); } }} />
          {answerError && (
            <p
              role="alert"
              className="mt-3 rounded-control border border-warning bg-warning-soft p-3 text-body text-warning"
            >
              {answerError}
            </p>
          )}
          <fieldset disabled={pending} className="mt-3 disabled:opacity-60">
            <legend className="text-caption font-bold text-muted">
              답변 확신도 <span className="font-normal text-subtle">(선택)</span>
            </legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {confidenceOptions.map((value) => (
                <label key={value} className="cursor-pointer">
                  <input
                    type="radio"
                    name="answer-confidence"
                    value={value}
                    checked={confidenceDraft?.id === id && confidenceDraft.value === value}
                    onChange={() => setConfidenceDraft({ id, value })}
                    className="peer sr-only"
                  />
                  <span className="inline-block rounded-control border border-line px-3 py-1.5 text-caption font-semibold text-muted peer-checked:border-primary-line peer-checked:bg-primary-soft peer-checked:text-primary-strong peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary">
                    {confidenceLabels[value]}
                  </span>
                </label>
              ))}
              {confidenceDraft?.id === id && (
                <button type="button" className="px-2 text-caption text-subtle underline" onClick={() => setConfidenceDraft(undefined)}>
                  선택 지우기
                </button>
              )}
            </div>
          </fieldset>
          <div className="mt-3 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-micro text-subtle">학습자료를 보지 않고 설명해보세요<br />{answer.length}자 · Ctrl+Enter</p>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="soft"
                aria-describedby="speech-input-help"
                disabled={pending || speechState === "stopping"}
                onClick={speechState === "listening" ? stopSpeech : startSpeech}
              >
                {speechState === "listening" ? "음성 입력 중지" : speechState === "stopping" ? "음성 처리 중…" : "음성으로 입력"}
              </Button>
              <Button type="submit" disabled={pending || speechState !== "idle" || !answer.trim()}>{pending ? "분석 중…" : "설명 보내기"}</Button>
            </div>
          </div>
          <p id="speech-input-help" className="mt-3 text-micro text-subtle">음성은 브라우저의 음성 인식 서비스에서 처리될 수 있어요.</p>
          <p role="status" className={speechMessage || speechState !== "idle" ? "mt-2 text-caption text-muted" : "sr-only"}>
            {speechMessage || (speechState === "listening" ? "듣고 있어요. 설명을 마치면 음성 입력을 중지해주세요." : speechState === "stopping" ? "마지막 음성을 텍스트로 바꾸고 있어요." : "")}
          </p>
          <p className="mt-3 text-micro text-subtle">정답을 맞히려 하지 않아도 괜찮아요. 지금 이해한 만큼 자신의 언어로 설명해주세요.</p>
        </form> : session.concept_available !== false && <div className="flex justify-end"><Button disabled={pending || starting} onClick={restart}>이 개념 다시 학습하기</Button></div>}
      </section>
      {!ended && <aside className="min-w-0 space-y-5 rounded-card border border-line bg-surface p-4 sm:p-5 lg:sticky lg:top-24"><div><p className="text-eyebrow font-bold text-primary-strong">실시간 분석</p><h2 className="mt-2 text-subheading font-bold">현재 이해 상태</h2><div className="mt-3"><StateBadge state={latest?.state ?? "not_studied"} /></div></div>
        <ul className="space-y-4">{latest?.elements.map((element) => <li key={element.element_id} className="text-caption"><p className="font-semibold text-muted">{element.text}</p><p className="mt-1 text-subtle">{element.importance === "core" ? "핵심" : "보조"} · {pending ? "이해 확인 중" : verdictLabels[element.verdict]}</p>{element.learner_quote && <blockquote className="mt-2 border-l-2 border-primary-line pl-2 text-subtle">“{element.learner_quote}”</blockquote>}</li>) ?? <li className="text-caption text-subtle">첫 설명을 보내면 이해 상태를 확인할 수 있어요.</li>}</ul>
        <div><p className="text-caption text-subtle">현재 이해도</p><p className="text-title-2 font-bold text-primary-strong">{latest ? `${latest.score}%` : "-"}</p><progress aria-label="현재 이해도" value={latest?.score ?? 0} max={100} className="h-2 w-full accent-primary" /></div>
        {!!latest?.feedback.unverified_statements?.length && <div className="rounded-control bg-primary-soft p-3 text-caption"><p className="font-bold text-primary-strong">자료에서 확인되지 않음</p>{latest.feedback.unverified_statements.map((s, i) => <p key={i} className="mt-2 text-muted">“{s.learner_quote}”</p>)}</div>}
        <div><h3 className="text-caption font-bold text-muted">연결된 학습자료</h3><ul className="mt-2 space-y-2 text-micro text-subtle">{evidence.map((e) => <li key={e.id}>{e.material_title} · {e.page_start}{e.page_end !== e.page_start ? `–${e.page_end}` : ""}쪽/슬라이드</li>)}</ul></div>
      </aside>}
    </div>
    {confirmExit && <Modal title="학습을 종료할까요?" onClose={() => !pending && setConfirmExit(false)} dismissible={false}><p className="text-body-lg text-muted">지금 종료하면 이 학습은 이어할 수 없어요. 마지막 판정은 저장됩니다.</p><div className="mt-6 flex justify-end gap-2"><Button variant="ghost" disabled={pending} onClick={() => setConfirmExit(false)}>계속 학습</Button><Button variant="danger" disabled={pending} onClick={finish}>학습 종료</Button></div></Modal>}
    {ended && <Link href={session.project_available === false ? "/records" : `/projects/${session.project_id}`} className={buttonStyles("ghost")}>{session.project_available === false ? "학습기록으로 돌아가기" : "프로젝트로 돌아가기"}</Link>}
  </div>;
}

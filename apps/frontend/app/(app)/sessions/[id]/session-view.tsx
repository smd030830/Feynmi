"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, buttonStyles } from "@/components/button";
import { Conversation, StateBadge } from "@/components/learning-feedback";
import { Modal } from "@/components/modal";
import { abortSession, abortSessionOnExit, apiErrorMessage, getSession, startSession, submitAnswer, type LearningSession } from "@/lib/api";
import { getFirebaseAuth } from "@/lib/firebase";

const steps = ["개념 설명", "추가 질문 1", "추가 질문 2", "추가 질문 3", "정리"];
const verdictLabels = { met: "충족", partial: "부분", missing: "누락", contradicted: "모순" };

export function SessionView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const [loaded, setLoaded] = useState<{ id: string; session?: LearningSession; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  const [answer, setAnswer] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [confirmExit, setConfirmExit] = useState(false);
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
  }, [id, pathname, router]);

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (!answer.trim() || live.current.pending || session?.status !== "in_progress") return;
    live.current.pending = true;
    setPending(true); setError("");
    try {
      const updated = await submitAnswer(id, answer.trim());
      setLoaded({ id, session: updated }); setAnswer("");
    } catch (err) {
      setError(apiErrorMessage(err));
      // 실패한 답변도 서버에 보관될 수 있으므로 대화를 다시 읽는다.
      try { setLoaded({ id, session: await getSession(id) }); } catch { /* 기존 대화와 입력을 유지한다. */ }
    } finally { live.current.pending = false; setPending(false); }
  }
  async function finish() {
    if (live.current.pending) return;
    live.current.pending = true;
    setPending(true); setError("");
    try { const updated = await abortSession(id); live.current.session = updated; live.current.pending = false; setPending(false); setLoaded({ id, session: updated }); setConfirmExit(false); router.push(`/projects/${updated.project_id}`); }
    catch (err) { setError(apiErrorMessage(err)); } finally { live.current.pending = false; setPending(false); }
  }
  async function restart() {
    if (!session || live.current.pending) return;
    live.current.pending = true;
    setPending(true); setError("");
    try { const next = await startSession(session.concept_id); live.current.pending = false; setPending(false); router.push(`/sessions/${next.id}`); }
    catch (err) { live.current.pending = false; setError(apiErrorMessage(err)); setPending(false); }
  }

  if (loaded?.id === id && loaded.error) return <div role="alert" className="rounded-card border border-line bg-surface p-8"><p>{loaded.error}</p><Button className="mt-4" onClick={() => setAttempt((n) => n + 1)}>다시 시도</Button></div>;
  if (!session) return <p aria-busy className="text-body text-subtle">학습을 불러오고 있어요…</p>;
  const latest = session.assessments.at(-1);
  const currentQuestion = session.messages.filter((m) => m.role === "question").at(-1)?.text;
  const ended = session.status !== "in_progress";
  const evidence = [...new Map(latest?.elements.flatMap((e) => e.evidence).map((e) => [e.id, e]) ?? []).values()];

  return <div className="space-y-7">
    <div className="flex items-center justify-between"><Link href={`/projects/${session.project_id}`} className="text-caption font-semibold text-subtle">{session.project_name} › {session.concept_title}</Link>{!ended && <Button variant="soft" disabled={pending} onClick={() => setConfirmExit(true)}>학습 종료</Button>}</div>
    <header className="flex items-end justify-between"><div><p className="text-eyebrow font-bold text-primary-strong">FEYNMAN 학습</p><h1 className="mt-2 text-title-1 font-bold">{session.concept_title}</h1></div><span className="text-caption text-subtle">{ended ? "중단된 학습" : `추가 질문 ${Math.max(0, 3 - session.followups_used)}회 남음`}</span></header>
    {!ended && <ol className="flex rounded-card border border-line bg-surface p-4" aria-label="학습 단계">{steps.map((step, i) => <li key={step} aria-current={i === session.followups_used ? "step" : undefined} className={`flex-1 text-center text-caption font-bold ${i === session.followups_used ? "text-primary-strong" : "text-subtle"}`}><span className={`mx-auto mb-2 flex size-7 items-center justify-center rounded-full ${i <= session.followups_used ? "bg-primary-soft text-primary-strong" : "bg-canvas"}`}>{i + 1}</span>{step}</li>)}</ol>}
    {error && <p role="alert" className="rounded-control bg-danger-soft p-4 text-body text-danger">{error}</p>}
    <div className={ended ? "" : "grid grid-cols-[minmax(0,1fr)_270px] items-start gap-6"}>
      <section className="min-w-0 space-y-6"><div className="flex justify-between"><h2 className="text-heading font-bold">{ended ? "중단된 학습의 대화" : "설명하며 이해하기"}</h2>{pending && <span role="status" className="text-caption text-primary-strong">대화 분석 중…</span>}</div>
        <Conversation messages={session.messages} assessments={session.assessments} />
        {!ended ? <form onSubmit={send} className="sticky bottom-5 rounded-card border border-primary-line bg-surface p-5 shadow-brand">
          <p className="text-caption font-bold text-primary-strong">현재 질문</p><p className="mt-1 text-body text-muted">{currentQuestion}</p>
          <label htmlFor="learner-answer" className="sr-only">나의 설명</label><textarea id="learner-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={pending} placeholder="내 말로 설명해보세요..." className="mt-4 min-h-36 w-full resize-y rounded-control border border-line p-4 text-body-lg disabled:opacity-60" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void send(); } }} />
          <div className="mt-3 flex items-center justify-between gap-3"><p className="text-micro text-subtle">학습자료를 보지 않고 설명해보세요<br />{answer.length}자 · Ctrl+Enter</p><Button type="submit" disabled={pending || !answer.trim()}>{pending ? "분석 중…" : "설명 보내기"}</Button></div>
          <p className="mt-3 text-micro text-subtle">정답을 맞히려 하지 않아도 괜찮아요. 지금 이해한 만큼 자신의 언어로 설명해주세요.</p>
        </form> : <div className="flex justify-end"><Button disabled={pending} onClick={restart}>이 개념 다시 학습하기</Button></div>}
      </section>
      {!ended && <aside className="sticky top-24 space-y-5 rounded-card border border-line bg-surface p-5"><div><p className="text-eyebrow font-bold text-primary-strong">실시간 분석</p><h2 className="mt-2 text-subheading font-bold">현재 이해 상태</h2><div className="mt-3"><StateBadge state={latest?.state ?? "not_studied"} /></div></div>
        <ul className="space-y-4">{latest?.elements.map((element) => <li key={element.element_id} className="text-caption"><p className="font-semibold text-muted">{element.text}</p><p className="mt-1 text-subtle">{element.importance === "core" ? "핵심" : "보조"} · {pending ? "이해 확인 중" : verdictLabels[element.verdict]}</p>{element.learner_quote && <blockquote className="mt-2 border-l-2 border-primary-line pl-2 text-subtle">“{element.learner_quote}”</blockquote>}</li>) ?? <li className="text-caption text-subtle">첫 설명을 보내면 이해 상태를 확인할 수 있어요.</li>}</ul>
        <div><p className="text-caption text-subtle">현재 이해도</p><p className="text-title-2 font-bold text-primary-strong">{latest ? `${latest.score}%` : "-"}</p><progress aria-label="현재 이해도" value={latest?.score ?? 0} max={100} className="h-2 w-full accent-primary" /></div>
        {!!latest?.feedback.unverified_statements?.length && <div className="rounded-control bg-primary-soft p-3 text-caption"><p className="font-bold text-primary-strong">자료에서 확인되지 않음</p>{latest.feedback.unverified_statements.map((s, i) => <p key={i} className="mt-2 text-muted">“{s.learner_quote}”</p>)}</div>}
        <div><h3 className="text-caption font-bold text-muted">연결된 학습자료</h3><ul className="mt-2 space-y-2 text-micro text-subtle">{evidence.map((e) => <li key={e.id}>{e.material_title} · {e.page_start}{e.page_end !== e.page_start ? `–${e.page_end}` : ""}쪽/슬라이드</li>)}</ul></div>
      </aside>}
    </div>
    {confirmExit && <Modal title="학습을 종료할까요?" onClose={() => !pending && setConfirmExit(false)} dismissible={false}><p className="text-body-lg text-muted">지금 종료하면 이 학습은 이어할 수 없어요. 마지막 판정은 저장됩니다.</p><div className="mt-6 flex justify-end gap-2"><Button variant="ghost" disabled={pending} onClick={() => setConfirmExit(false)}>계속 학습</Button><Button variant="danger" disabled={pending} onClick={finish}>학습 종료</Button></div></Modal>}
    {ended && <Link href={`/projects/${session.project_id}`} className={buttonStyles("ghost")}>프로젝트로 돌아가기</Link>}
  </div>;
}

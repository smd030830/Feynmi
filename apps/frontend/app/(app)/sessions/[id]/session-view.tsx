"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, buttonStyles } from "@/components/button";
import { confidenceLabels, Conversation } from "@/components/learning-feedback";
import { useAccount } from "@/components/account-provider";
import { Modal } from "@/components/modal";
import { abortSession, apiErrorMessage, ApiError, getSession, submitAnswer, type AnswerConfidence, type LearningSession } from "@/lib/api";
import { useSpeechDictation } from "@/lib/use-speech-dictation";
import { useStartLearning } from "@/lib/use-start-learning";

const confidenceOptions = ["high", "uncertain", "low"] as const;

export function SessionView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAccount();
  const draftKey = user?.uid ? `feynmi:answer-draft:${user.uid}:${id}` : "";
  const [loaded, setLoaded] = useState<{ id: string; session?: LearningSession; error?: string }>();
  const [attempt, setAttempt] = useState(0);
  const [draft, setDraft] = useState<{ key: string; text: string }>({ key: "", text: "" });
  const draftRef = useRef(draft);
  const answer = draft.key === draftKey ? draft.text : "";
  const [confidenceDraft, setConfidenceDraft] = useState<{ id: string; value: AnswerConfidence }>();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [answerError, setAnswerError] = useState("");
  const [confirmExit, setConfirmExit] = useState(false);
  const { begin, starting, startError } = useStartLearning();
  function setAnswer(value: string | ((previous: string) => string)) {
    const current = draftRef.current.key === draftKey ? draftRef.current.text : "";
    const text = typeof value === "function" ? value(current) : value;
    const next = { key: draftKey, text };
    draftRef.current = next;
    if (draftKey) {
      try {
        if (text) localStorage.setItem(draftKey, text);
        else localStorage.removeItem(draftKey);
      } catch { /* 저장소를 쓸 수 없어도 입력과 제출은 가능하다. */ }
    }
    setDraft(next);
  }
  const { state: speechState, message: speechMessage, start: startSpeech, stop: stopSpeech, abort: abortSpeech, isActive: speechIsActive } =
    useSpeechDictation(id, (text) => setAnswer((value) => value && !/\s$/.test(value) ? `${value} ${text}` : value + text));
  const live = useRef<{ session?: LearningSession; pending: boolean }>({ pending: false });
  const session = loaded?.id === id ? loaded.session : undefined;

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => {
      if (!active || !draftKey || draftRef.current.key === draftKey) return;
      let text = "";
      try { text = localStorage.getItem(draftKey) ?? ""; }
      catch { /* 저장소가 차단되면 빈 초안으로 시작한다. */ }
      const restored = { key: draftKey, text };
      draftRef.current = restored;
      setDraft(restored);
    });
    return () => { active = false; };
  }, [draftKey]);

  useEffect(() => {
    let cancelled = false;
    getSession(id).then((value) => {
      if (!cancelled) {
        live.current.session = value;
        live.current.pending = false;
        setPending(false);
        setLoaded({ id, session: value });
      }
    }).catch((err) => !cancelled && setLoaded({ id, error: apiErrorMessage(err) }));
    return () => { cancelled = true; };
  }, [id, attempt]);

  useEffect(() => {
    live.current.session = session;
    if (session?.status === "completed") router.replace(`/sessions/${id}/result`);
  }, [session, id, router]);

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

  return <div className="space-y-7">
    <div className="flex items-center justify-between">{session.project_available === false ? <p className="text-caption font-semibold text-subtle">{session.project_name} (삭제된 프로젝트) › {session.concept_title}</p> : <Link href={`/projects/${session.project_id}`} className="text-caption font-semibold text-subtle">{session.project_name} › {session.concept_title}</Link>}{!ended && <Button variant="soft" disabled={pending} onClick={() => { stopSpeech(); setConfirmExit(true); }}>학습 종료</Button>}</div>
    <header className="flex items-end justify-between gap-4"><div><p className="text-eyebrow font-bold text-primary-strong">FEYNMAN 학습</p><h1 className="mt-2 text-title-1 font-bold">{session.concept_title}</h1></div><span className="shrink-0 text-caption text-subtle">{ended ? "중단된 학습" : "최대 5문항 · 이해도 100% 달성 시 조기 종료"}</span></header>
    {session.concept_available === false && <p className="rounded-control bg-canvas p-4 text-body text-muted">학습자료가 삭제되어 이 개념을 다시 학습할 수 없어요. 당시 설명과 피드백은 아래에서 볼 수 있어요.</p>}
    {!ended && session.followups_used > 0 && <p aria-live="polite" className="text-caption font-bold text-primary-strong">추가 질문 {session.followups_used}</p>}
    {(error || startError) && <p role="alert" className="rounded-control bg-danger-soft p-4 text-body text-danger">{error || startError}</p>}
    <div className="min-w-0">
      <section className="min-w-0 space-y-6"><div className="flex justify-between"><h2 className="text-heading font-bold">{ended ? "중단된 학습의 대화" : "설명하며 이해하기"}</h2>{pending && <span role="status" className="text-caption text-primary-strong">대화 분석 중…</span>}</div>
        <Conversation messages={session.messages} assessments={session.assessments} showFeedback={false} />
        {!ended ? <form onSubmit={send} className="min-w-0 rounded-card border border-primary-line bg-surface p-4 shadow-brand sm:p-5">
          {currentQuestion && hintSource && (
            <details key={currentQuestion.id} className="rounded-control border border-line bg-canvas p-3">
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
          <div className="mt-3 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-end">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="soft"
                aria-describedby="speech-input-help"
                title="음성은 브라우저의 음성 인식 서비스에서 처리될 수 있어요."
                disabled={pending || speechState === "stopping"}
                onClick={speechState === "listening" ? stopSpeech : startSpeech}
              >
                {speechState === "listening" ? "음성 입력 중지" : speechState === "stopping" ? "음성 처리 중…" : "음성으로 입력"}
              </Button>
              <Button type="submit" disabled={pending || speechState !== "idle" || !answer.trim()}>{pending ? "분석 중…" : "설명 보내기"}</Button>
            </div>
          </div>
          <p id="speech-input-help" className="sr-only">음성은 브라우저의 음성 인식 서비스에서 처리될 수 있어요.</p>
          <p role="status" className={speechMessage || speechState !== "idle" ? "mt-2 text-caption text-muted" : "sr-only"}>
            {speechMessage || (speechState === "listening" ? "듣고 있어요. 설명을 마치면 음성 입력을 중지해주세요." : speechState === "stopping" ? "마지막 음성을 텍스트로 바꾸고 있어요." : "")}
          </p>        </form> : session.concept_available !== false && <div className="flex justify-end"><Button disabled={pending || starting} onClick={restart}>이 개념 다시 학습하기</Button></div>}
      </section>

    </div>
    {confirmExit && <Modal title="학습을 종료할까요?" onClose={() => !pending && setConfirmExit(false)} dismissible={false}><p className="text-body-lg text-muted">지금 종료하면 이 학습은 이어할 수 없어요. 마지막 판정은 저장됩니다.</p><div className="mt-6 flex justify-end gap-2"><Button variant="ghost" disabled={pending} onClick={() => setConfirmExit(false)}>계속 학습</Button><Button variant="danger" disabled={pending} onClick={finish}>학습 종료</Button></div></Modal>}
    {ended && <Link href={session.project_available === false ? "/records" : `/projects/${session.project_id}`} className={buttonStyles("ghost")}>{session.project_available === false ? "학습기록으로 돌아가기" : "프로젝트로 돌아가기"}</Link>}
  </div>;
}

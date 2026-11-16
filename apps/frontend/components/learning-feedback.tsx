import type { AnswerConfidence, Assessment, ConceptState, LearningMessage } from "@/lib/api";

export const confidenceLabels: Record<AnswerConfidence, string> = {
  high: "확실해요",
  uncertain: "조금 헷갈려요",
  low: "잘 모르겠어요",
};

export const stateLabels: Record<ConceptState, string> = {
  understood: "이해", partial: "부분 이해", misconception: "오개념", not_studied: "미학습",
};
const stateColors: Record<ConceptState, string> = {
  understood: "bg-success-soft text-success", partial: "bg-warning-soft text-warning",
  misconception: "bg-danger-soft text-danger", not_studied: "bg-canvas text-subtle",
};
export function StateBadge({ state }: { state: ConceptState }) {
  return <span className={`inline-flex rounded-full px-3 py-1 text-caption font-bold ${stateColors[state]}`}>{stateLabels[state]}</span>;
}
export function FeedbackList({ items }: { items: string[] }) {
  return items.length ? <ul className="list-disc space-y-2 pl-5 text-body text-muted">{items.map((item, i) => <li key={i} className="whitespace-pre-line">{item}</li>)}</ul> : <p className="text-body text-subtle">해당 없음</p>;
}
function ImprovementFeedback({ assessment }: { assessment: Assessment }) {
  const feedback = assessment.feedback;
  // 완료된 세션은 힌트 대신 상세 피드백을 공개한다. 없는 힌트를 "해당 없음"으로 표시하지 않는다.
  const detailed = feedback.missing !== undefined || feedback.incorrect !== undefined;
  const items = detailed
    ? [...(feedback.missing ?? []), ...(feedback.incorrect ?? [])]
    : feedback.missing_hint ?? [];
  const needsWork = assessment.state === "partial" || assessment.state === "misconception"
    || assessment.elements.some((element) => element.verdict !== "met");
  if (!needsWork) return <p className="text-body text-subtle">추가로 보완할 부분이 없어요.</p>;
  const fallback = detailed
    ? "아직 설명이 충분하지 않은 핵심 요소가 있어요. 자료를 확인하고 다시 학습해보세요."
    : "현재 설명만으로는 핵심 요소를 충분히 확인하기 어려워요. 질문에서 묻는 조건이나 작동 방식을 짧게 덧붙여보세요.";
  return <>
    <p className="text-caption font-bold text-warning">{detailed ? "보완이 필요한 부분" : "짧은 풀이와 힌트"}</p>
    <FeedbackList items={items.length ? items : [fallback]} />
  </>;
}
export function Conversation({ messages, assessments }: { messages: LearningMessage[]; assessments: Assessment[] }) {
  return <div className="space-y-5">{messages.map((message, index) => {
    // 답변 평가 실패 시 평가 없는 답변도 보존된다. 평가 시각 직전의 답변에만 노트를 붙인다.
    const assessment = message.role === "answer" ? assessments.find((item) => {
      if (item.answer_message_id) return item.answer_message_id === message.id;
      const next = messages.slice(index + 1).find((m) => m.role === "answer");
      return Date.parse(item.created_at) >= Date.parse(message.created_at) && (!next || Date.parse(item.created_at) < Date.parse(next.created_at));
    }) : undefined;
    const answerIndex = messages.slice(0, index + 1).filter((item) => item.role === "answer").length;
    return <div key={message.id} className={message.role === "answer" ? "ml-2 sm:ml-8" : "mr-2 sm:mr-8"}>
      {message.role === "question" ? (
        <div className="min-w-0 overflow-hidden rounded-card border border-primary-line bg-primary-soft p-4 shadow-sm sm:p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-control bg-primary text-white" aria-hidden="true">✦</span>
              <span className="text-caption font-bold text-primary-strong">FEYNMI AI</span>
            </div>
            <span className="rounded-full border border-primary-line bg-surface px-3 py-1 text-micro font-bold text-primary-strong">
              생각을 확장하는 질문
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words text-heading font-bold leading-relaxed text-primary-strong sm:text-subheading">
            {message.text}
          </p>
        </div>
      ) : (
        <>
          <p className="mb-2 text-caption font-bold text-subtle">
            나의 설명 {answerIndex}
            {message.confidence && (
              <span className="ml-2 font-normal">· 답변 확신도 {confidenceLabels[message.confidence]}</span>
            )}
          </p>
          <div className="min-w-0 whitespace-pre-wrap break-words rounded-card bg-primary-soft p-4 text-body-lg text-text sm:p-5">
            {message.text}
          </div>
        </>
      )}
      {assessment && <div className="mt-3 space-y-3 rounded-control border border-primary-line bg-surface p-4">
        <div className="flex items-center gap-2"><StateBadge state={assessment.state} /><span className="text-body font-bold text-primary-strong">{assessment.score}%</span></div>
        <ImprovementFeedback assessment={assessment} />
      </div>}
    </div>;
  })}</div>;
}

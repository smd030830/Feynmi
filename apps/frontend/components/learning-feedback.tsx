import type { Assessment, ConceptState, LearningMessage } from "@/lib/api";

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
export function Conversation({ messages, assessments }: { messages: LearningMessage[]; assessments: Assessment[] }) {
  return <div className="space-y-5">{messages.map((message, index) => {
    // 답변 평가 실패 시 평가 없는 답변도 보존된다. 평가 시각 직전의 답변에만 노트를 붙인다.
    const assessment = message.role === "answer" ? assessments.find((item) => {
      const next = messages.slice(index + 1).find((m) => m.role === "answer");
      return Date.parse(item.created_at) >= Date.parse(message.created_at) && (!next || Date.parse(item.created_at) < Date.parse(next.created_at));
    }) : undefined;
    const answerIndex = messages.slice(0, index + 1).filter((item) => item.role === "answer").length;
    return <div key={message.id} className={message.role === "answer" ? "ml-8" : "mr-8"}>
      <p className="mb-2 text-caption font-bold text-subtle">{message.role === "question" ? "AI 질문" : `나의 설명 ${answerIndex}`}</p>
      <div className={`whitespace-pre-wrap rounded-card p-5 text-body-lg ${message.role === "answer" ? "bg-primary-soft text-text" : "border border-line bg-surface text-muted"}`}>{message.text}</div>
      {assessment && <div className="mt-3 space-y-3 rounded-control border border-primary-line bg-surface p-4">
        <div className="flex items-center gap-2"><StateBadge state={assessment.state} /><span className="text-body font-bold text-primary-strong">{assessment.score}%</span></div>
        <p className="text-caption font-bold text-success">잘 이해한 부분</p><FeedbackList items={assessment.feedback.correct} />
        <p className="text-caption font-bold text-warning">생각해볼 부분</p><FeedbackList items={assessment.feedback.missing_hint ?? []} />
      </div>}
    </div>;
  })}</div>;
}

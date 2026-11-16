import type { Assessment, LearningSession } from "@/lib/api";

type Element = Assessment["elements"][number];

type Misconception = {
  before: Element;
  highConfidence: boolean;
  lastContradiction: number;
};

const verdictLabels = {
  met: "충족",
  partial: "부분 충족",
  missing: "누락",
  contradicted: "모순",
};

function normalize(text: string) {
  return text.trim().replace(/\s+/g, " ");
}

function comparisons({ messages, assessments }: LearningSession) {
  const answers = messages.filter((message) => message.role === "answer");
  const answerById = new Map(answers.map((answer) => [answer.id, answer]));
  const answerAt = assessments.map((assessment) => {
    if (assessment.answer_message_id) return answerById.get(assessment.answer_message_id);
    const time = Date.parse(assessment.created_at);
    if (answers.some((answer) => Date.parse(answer.created_at) === time)) return undefined;
    return answers.findLast((answer) => Date.parse(answer.created_at) < time);
  });

  function sourceOfQuote(quote: string, index: number) {
    const latest = answerAt[index];
    if (!quote || !latest) return undefined;
    if (normalize(latest.text).includes(quote)) return latest;
    // Cumulative assessment can quote an earlier answer. Require a unique match.
    const matches = answers.filter((answer) => answer.seq < latest.seq && normalize(answer.text).includes(quote));
    return matches.length === 1 ? matches[0] : undefined;
  }

  const misconceptions = new Map<string, Misconception>();
  for (const [index, assessment] of assessments.entries()) {
    for (const element of assessment.elements) {
      if (element.importance !== "core" || element.verdict !== "contradicted") continue;
      const quote = normalize(element.learner_quote ?? "");
      const highConfidence = !!assessment.answer_message_id && sourceOfQuote(quote, index)?.confidence === "high";
      const existing = misconceptions.get(element.element_id);
      misconceptions.set(element.element_id, {
        before: existing && (existing.highConfidence || !highConfidence) ? existing.before : element,
        highConfidence: (existing?.highConfidence ?? false) || highConfidence,
        lastContradiction: index,
      });
    }
  }

  return (assessments.at(-1)?.elements ?? []).flatMap((final) => {
    const misconception = misconceptions.get(final.element_id);
    if (!misconception) return [];
    const { before, highConfidence, lastContradiction } = misconception;
    const quote = normalize(final.learner_quote ?? "");
    const previousAnswer = answerAt[lastContradiction];
    const finalAnswer = sourceOfQuote(quote, assessments.length - 1);
    const hasNewQuote = quote !== normalize(before.learner_quote ?? "")
      && !!previousAnswer && !!finalAnswer && finalAnswer.seq > previousAnswer.seq;
    return [{
      before,
      final,
      highConfidence,
      afterQuote: hasNewQuote ? final.learner_quote : null,
      priority: highConfidence && final.verdict !== "met",
    }];
  }).sort((a, b) => Number(b.priority) - Number(a.priority));
}

export function MisconceptionReview({ session }: { session: LearningSession }) {
  const entries = comparisons(session);
  if (!entries.length) return null;

  return (
    <section aria-labelledby="misconception-review" className="rounded-card border border-line bg-surface p-6">
      <h2 id="misconception-review" className="text-heading font-bold">오개념 교정 전후</h2>
      <div className="mt-4 space-y-4">
        {entries.map(({ before, final, highConfidence, afterQuote, priority }) => {
          const evidence = new Map([...before.evidence, ...final.evidence].map((item) => [
            JSON.stringify([item.material_title, item.page_start, item.page_end]), item,
          ]));
          return (
            <article key={before.element_id} className="rounded-control border border-line p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-body-lg font-bold">{before.text}</h3>
                {priority && <span className="rounded-full bg-warning-soft px-3 py-1 text-caption font-bold text-warning">우선 복습</span>}
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="min-w-0 rounded-control bg-danger-soft p-3">
                  <p className="text-caption font-bold text-danger">
                    {highConfidence ? "확신한 답변에서 오개념 발견" : "오개념이 드러난 설명"}
                  </p>
                  {before.learner_quote && <blockquote className="mt-2 whitespace-pre-wrap break-words text-body text-muted">“{before.learner_quote}”</blockquote>}
                </div>
                <div className={`min-w-0 rounded-control p-3 ${final.verdict === "met" ? "bg-success-soft" : "bg-canvas"}`}>
                  <p className={`text-caption font-bold ${final.verdict === "met" ? "text-success" : "text-muted"}`}>
                    최종 판정 · {verdictLabels[final.verdict]}
                  </p>
                  {afterQuote
                    ? <blockquote className="mt-2 whitespace-pre-wrap break-words text-body text-muted">“{afterQuote}”</blockquote>
                    : <p className="mt-2 text-body text-subtle">이후 답변에서 비교할 새 문장을 확인하지 못했어요.</p>}
                </div>
              </div>
              {evidence.size > 0 && (
                <div className="mt-3">
                  <p className="text-caption font-bold text-muted">자료 근거</p>
                  <ul className="mt-1 space-y-1 text-caption text-subtle">
                    {Array.from(evidence, ([key, item]) => (
                      <li key={key}>{item.material_title} · {item.page_start}{item.page_end !== item.page_start ? `–${item.page_end}` : ""}쪽/슬라이드</li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

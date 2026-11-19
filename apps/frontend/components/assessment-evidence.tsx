import type { Assessment } from "@/lib/api";

const verdictLabels = {
  met: "충족",
  partial: "부분",
  missing: "누락",
  contradicted: "모순",
};

export function AssessmentEvidence({ assessments }: { assessments: Assessment[] }) {
  if (assessments.length === 0) return null;

  return (
    <details className="rounded-card border border-line bg-surface p-6">
      <summary className="cursor-pointer text-subheading font-bold">판정 근거 자세히 보기</summary>
      <div className="mt-4 space-y-3">
        {assessments.toReversed().map((assessment, index) => (
          <details key={assessment.id} open={index === 0} className="rounded-control border border-line p-3">
            <summary className="cursor-pointer text-body font-bold">
              {index === 0 ? "최종 판정" : `${assessments.length - index}차 판정`} · {assessment.score}%
            </summary>
            <div className="mt-3 space-y-2">
              {assessment.elements.map((element) => (
                <details key={element.element_id} className="rounded-control bg-canvas p-3">
                  <summary className="cursor-pointer break-words text-body font-semibold">
                    <span className="text-primary-strong">{verdictLabels[element.verdict]}</span> · {element.text}
                  </summary>
                  {element.note && <p className="mt-2 break-words text-caption text-muted">{element.note}</p>}
                  <div className="mt-3 grid min-w-0 gap-3 md:grid-cols-2">
                    <div className="min-w-0">
                      <p className="text-caption font-bold">내 답변의 근거 문장</p>
                      {element.learner_quote
                        ? <blockquote className="mt-1 break-words text-caption text-muted">“{element.learner_quote}”</blockquote>
                        : <p className="mt-1 text-caption text-subtle">이 항목에 연결된 답변 문장이 없어요.</p>}
                    </div>
                    <div className="min-w-0">
                      <p className="text-caption font-bold">학습자료의 근거</p>
                      {element.evidence.length > 0 ? (
                        <ul className="mt-1 space-y-2">
                          {element.evidence.map((source) => (
                            <li key={source.id} className="break-words text-caption text-muted">
                              <p className="font-semibold">{source.material_title} · {source.page_start}{source.page_end !== source.page_start ? `–${source.page_end}` : ""}쪽/슬라이드</p>
                            </li>
                          ))}
                        </ul>
                      ) : <p className="mt-1 text-caption text-subtle">이 항목에 연결된 자료 근거가 없어요.</p>}
                    </div>
                  </div>
                </details>
              ))}
            </div>
          </details>
        ))}
      </div>
    </details>
  );
}

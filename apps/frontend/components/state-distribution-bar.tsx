import type { StateCounts } from "@/lib/api";

// PRD FR-2.3 상태와 design-system 1.4 의미색
const states: { key: keyof StateCounts; label: string; dot: string }[] = [
  { key: "understood", label: "이해", dot: "bg-success-icon" },
  { key: "partial", label: "부분 이해", dot: "bg-warning-icon" },
  { key: "misconception", label: "오개념", dot: "bg-danger-icon" },
  { key: "not_studied", label: "미학습", dot: "bg-[#cbd5e1]" },
];

// design-system 8.2 State distribution bar: 6px 바 + 아래 micro 범례 숫자
export function StateDistributionBar({ counts }: { counts: StateCounts }) {
  const total = states.reduce((sum, state) => sum + counts[state.key], 0);
  return (
    <div>
      <div className="flex h-1.5 overflow-hidden rounded-full bg-[#eef0f4]">
        {total > 0 &&
          states.map(
            (state) =>
              counts[state.key] > 0 && (
                <span
                  key={state.key}
                  className={state.dot}
                  style={{ width: `${(counts[state.key] / total) * 100}%` }}
                />
              ),
          )}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-micro text-subtle">
        {states.map((state) => (
          <li key={state.key} className="flex items-center gap-1.5">
            <span className={`size-1.5 rounded-full ${state.dot}`} aria-hidden />
            {state.label} <span className="font-bold text-muted">{counts[state.key]}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

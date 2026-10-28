// design-system 8.1 Progress ring: 가운데 점수 + "이해도". 점수가 없으면 "-"
export function ProgressRing({ score }: { score: number | null }) {
  const degree = (score ?? 0) * 3.6;
  return (
    <div
      role="img"
      aria-label={score === null ? "이해도 없음" : `이해도 ${score}%`}
      className="flex size-[72px] shrink-0 items-center justify-center rounded-full"
      style={{ background: `conic-gradient(#6366f1 ${degree}deg, #eaecf3 0)` }}
    >
      <div className="flex size-[58px] flex-col items-center justify-center rounded-full bg-surface">
        <span className="text-subheading font-bold leading-none text-text">
          {score === null ? "-" : `${score}%`}
        </span>
        <span className="mt-1 text-micro leading-none text-subtle">이해도</span>
      </div>
    </div>
  );
}

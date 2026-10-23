import { useId } from "react";

// design-system 7.2: 42×42 "F" 마크 + 워드마크. 경로는 시안 원본이 없어 직접 그렸다.
export function LogoMark({ size = 35 }: { size?: number }) {
  const gradientId = useId();
  return (
    <svg viewBox="0 0 42 42" width={size} height={size} aria-hidden>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="0.55" stopColor="#a78bfa" />
          <stop offset="1" stopColor="#7dd3fc" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${gradientId})`}
        d="M13.5 5H31a3.5 3.5 0 0 1 0 7H17v5.5h10a3.5 3.5 0 0 1 0 7H17V35a3.5 3.5 0 0 1-7 0V8.5A3.5 3.5 0 0 1 13.5 5z"
      />
      <path
        d="M17 29c4-1 8-4 10-9"
        fill="none"
        stroke="#fff"
        strokeOpacity={0.42}
        strokeWidth={1.4}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Logo({ size = 35 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="font-brand text-[22px] font-extrabold tracking-[-1px] text-[#27314d]">
        Feynmi
      </span>
    </span>
  );
}

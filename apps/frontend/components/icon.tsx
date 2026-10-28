import type { ReactNode, SVGProps } from "react";

// design-system 7.1: 시안 SVG를 옮기는 컴포넌트. 시안 원본이 저장소에 없어
// 현재 경로는 같은 속성(24 viewBox, stroke 1.8)으로 직접 그린 것이다. 원본으로 교체 필요.
const paths = {
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m4 7.5 8 5.5 8-5.5" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2.5" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 5 6v5.5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9V6z" />
      <path d="m9 12 2.2 2.2L15 10.4" />
    </>
  ),
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  home: (
    <>
      <path d="M4 11l8-6.5 8 6.5" />
      <path d="M6 10v9.5h12V10" />
      <path d="M10 19.5v-5h4v5" />
    </>
  ),
  folder: <path d="M3.5 7a2 2 0 0 1 2-2H10l2 2.5h6.5a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />,
  chart: (
    <>
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  file: (
    <>
      <path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z" />
      <path d="M14 3.5V8h4.5" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  chevron: <path d="m9 6 6 6-6 6" />,
  bell: (
    <>
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </>
  ),
  logout: (
    <>
      <path d="M10 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H10" />
      <path d="M15 8l4 4-4 4M19 12H9.5" />
    </>
  ),
  more: (
    <>
      <circle cx="5.5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="18.5" cy="12" r="1" />
    </>
  ),
  book: (
    <>
      <path d="M12 6.5C10.5 5 8 4.5 4.5 5v13c3.5-.5 6 0 7.5 1.5 1.5-1.5 4-2 7.5-1.5V5C16 4.5 13.5 5 12 6.5z" />
      <path d="M12 6.5v13" />
    </>
  ),
  brain: (
    <>
      <path d="M9 4.5a3 3 0 0 0-3 3 3 3 0 0 0-2 2.8 3 3 0 0 0 1.2 2.4A3 3 0 0 0 6 17a3 3 0 0 0 3 2.5 3 3 0 0 0 3-2.5V7.5a3 3 0 0 0-3-3z" />
      <path d="M15 4.5a3 3 0 0 1 3 3 3 3 0 0 1 2 2.8 3 3 0 0 1-1.2 2.4A3 3 0 0 1 18 17a3 3 0 0 1-3 2.5 3 3 0 0 1-3-2.5" />
    </>
  ),
  spark: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
  target: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof paths;

type IconProps = Omit<SVGProps<SVGSVGElement>, "name"> & {
  name: IconName;
  size?: number;
};

export function Icon({ name, size = 20, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      {paths[name]}
    </svg>
  );
}

// Google "G" 마크 (로그인 버튼 전용, 공급자 색 유지)
export function GoogleIcon({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.58-5.17 3.58-8.81z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.88-3a7.2 7.2 0 0 1-10.7-3.78H1.34v3.09A12 12 0 0 0 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.36 14.31a7.2 7.2 0 0 1 0-4.62V6.6H1.34a12 12 0 0 0 0 10.8l4.02-3.09z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.76 0 3.34.6 4.58 1.8l3.44-3.44A11.95 11.95 0 0 0 12 0 12 12 0 0 0 1.34 6.6l4.02 3.09A7.16 7.16 0 0 1 12 4.75z"
      />
    </svg>
  );
}

"use client";

import { usePathname } from "next/navigation";

// design-system 9.1 상단 바 왼쪽의 화면 이름
const titles: [prefix: string, title: string][] = [
  ["/projects", "프로젝트"],
  ["/records", "학습기록"],
  ["/settings", "설정"],
];

export function TopBarTitle() {
  const pathname = usePathname();
  const title = titles.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "홈";
  return <span className="text-caption font-bold text-subtle">{title}</span>;
}

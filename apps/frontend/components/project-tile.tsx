import type { ProjectColor } from "@/lib/api";

// design-system 1.3 강조색 쌍. 프로젝트 이니셜 타일과 프로젝트 색 표시에 쓴다.
export const projectTones: Record<ProjectColor, string> = {
  indigo: "bg-[#eef2ff] text-[#4f46e5]",
  lavender: "bg-[#f5f3ff] text-[#6d28d9]",
  cyan: "bg-[#ecfeff] text-[#0e7490]",
};

const sizes = {
  md: "size-[42px] rounded-[12px] text-heading",
  lg: "size-16 rounded-[16px] text-title-2",
} as const;

// 이름의 첫 글자를 이니셜로 쓴다 (PRD FR-1.0, design-system 2.1)
export function ProjectTile({
  name,
  color,
  size = "md",
}: {
  name: string;
  color: ProjectColor;
  size?: keyof typeof sizes;
}) {
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center font-bold shadow-brand-sm ${sizes[size]} ${projectTones[color]}`}
    >
      {Array.from(name.trim())[0]?.toUpperCase() ?? ""}
    </span>
  );
}

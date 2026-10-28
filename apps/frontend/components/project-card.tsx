import Link from "next/link";
import { Icon } from "@/components/icon";
import { ProjectTile } from "@/components/project-tile";
import { StateDistributionBar } from "@/components/state-distribution-bar";
import type { Project } from "@/lib/api";

const cardBase =
  "flex min-h-[236px] flex-col rounded-card border bg-surface p-5 transition duration-200 ease-out hover:-translate-y-0.5 hover:border-primary-line hover:shadow-[0_8px_22px_rgba(15,23,42,0.05)]";

// design-system 9.7·9.9 프로젝트 카드: 이니셜 타일, 이름, 최근 학습 개념, 이해도, 진행 바, 상태 분포 바
export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/projects/${project.id}`} className={`${cardBase} border-line`}>
      <ProjectTile name={project.name} color={project.color} />
      <p className="mt-4 truncate text-subheading font-bold text-text">{project.name}</p>
      {/* 최근 학습 개념은 세션(FM-030) 이후 채운다 */}
      <p className="truncate text-caption text-subtle">아직 학습한 개념이 없어요</p>

      <div className="mt-auto pt-5">
        <div className="flex items-baseline justify-between">
          <span className="text-caption text-subtle">이해도</span>
          <span className="text-body font-bold text-text">
            {project.score === null ? "-" : `${project.score}%`}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#eef0f4]">
          <div
            className="h-full rounded-full bg-[linear-gradient(90deg,#6366f1,#8b5cf6)]"
            style={{ width: `${project.score ?? 0}%` }}
          />
        </div>
        <div className="mt-4">
          <StateDistributionBar counts={project.state_counts} />
        </div>
      </div>
    </Link>
  );
}

// "새 프로젝트" 점선 카드 (design-system 9.7)
export function NewProjectCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${cardBase} items-center justify-center gap-3 border-dashed border-[#cbd5e1] text-muted hover:text-primary-strong`}
    >
      <span className="flex size-[42px] items-center justify-center rounded-[12px] bg-primary-soft text-primary">
        <Icon name="plus" size={20} />
      </span>
      <span className="text-body font-bold">새 프로젝트</span>
    </button>
  );
}

import type { Metadata } from "next";
import { buttonStyles } from "@/components/button";
import { GreetingEyebrow, TodayLabel } from "@/components/greeting";
import { Icon, type IconName } from "@/components/icon";

export const metadata: Metadata = { title: "홈 · Feynmi" };

// 임시 사용자와 빈 데이터. 프로젝트·세션 API(FM-024, FM-030~)가 생기면 실제 값으로 교체한다.
const NICKNAME = "admin";

const stats: { icon: IconName; label: string; value: string; unit?: string; tone: string }[] = [
  { icon: "target", label: "전체 이해도", value: "-", tone: "bg-[#f0fdf4] text-[#16a34a]" },
  { icon: "book", label: "학습 개념", value: "0", unit: "개", tone: "bg-[#eef2ff] text-[#6366f1]" },
  { icon: "clock", label: "학습 일수", value: "0", unit: "일", tone: "bg-[#f5f3ff] text-[#8b5cf6]" },
];

const cycle: { icon: IconName; label: string; tone: string }[] = [
  { icon: "book", label: "개념", tone: "bg-[#eef2ff] text-[#6366f1]" },
  { icon: "spark", label: "AI 질문", tone: "bg-[#ecfeff] text-[#0891b2]" },
  { icon: "target", label: "이해 분석", tone: "bg-[#f0fdf4] text-[#16a34a]" },
];

export default function HomePage() {
  return (
    <div className="flex flex-col gap-9">
      {/* 인사 줄 */}
      <div className="flex items-end justify-between">
        <div>
          <GreetingEyebrow />
          <h1 className="mt-1 text-title-1 font-bold text-text">안녕하세요, {NICKNAME}님</h1>
          <p className="text-body-lg text-muted">오늘은 무엇을 이해해볼까요?</p>
        </div>
        <TodayLabel />
      </div>

      {/* 히어로: 취약 개념이 없으므로 새 프로젝트 만들기 (FR-4.3) */}
      <section className="relative flex items-center justify-between overflow-hidden rounded-hero border border-[#e5e7ff] bg-[linear-gradient(125deg,#eef2ff_0%,#f4f1ff_53%,#effaff_100%)] px-12 py-[38px]">
        <div className="absolute -right-16 -top-20 size-64 rounded-full bg-white/50" aria-hidden />
        <div className="relative">
          <p className="text-eyebrow font-extrabold uppercase text-primary-strong">
            Feynman Learning
          </p>
          <h2 className="mt-3 text-title-2 font-bold text-text">
            내 말로 설명하면,
            <br />
            이해한 만큼 보여요.
          </h2>
          <button type="button" className={buttonStyles("primary", "mt-6")}>
            <Icon name="plus" size={18} />
            새 프로젝트 만들기
          </button>
        </div>
        <ol className="relative mr-6 flex items-center gap-3" aria-label="학습 순환">
          {cycle.map((step, index) => (
            <li key={step.label} className="flex items-center gap-3">
              <div className="flex flex-col items-center gap-2">
                <span
                  className={`flex size-14 items-center justify-center rounded-2xl shadow-brand-sm ${step.tone}`}
                >
                  <Icon name={step.icon} size={24} />
                </span>
                <span className="text-micro font-bold text-muted">{step.label}</span>
              </div>
              {index < cycle.length - 1 && (
                <Icon name="arrow" size={16} className="mb-6 text-placeholder" />
              )}
            </li>
          ))}
        </ol>
      </section>

      {/* 학습 개요 (FR-4.9) */}
      <section aria-labelledby="overview-title">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 id="overview-title" className="text-heading font-bold text-text">
            학습 개요
          </h2>
          <span className="text-caption text-subtle">지난 30일 기준</span>
        </div>
        <div className="grid grid-cols-3 gap-3.5">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="flex items-center gap-3.5 rounded-card border border-line bg-surface p-5"
            >
              <span
                className={`flex size-[38px] shrink-0 items-center justify-center rounded-[10px] ${stat.tone}`}
              >
                <Icon name={stat.icon} size={20} />
              </span>
              <div>
                <p className="text-caption text-subtle">{stat.label}</p>
                <p className="text-title-2 font-bold text-text">
                  {stat.value}
                  {stat.unit && (
                    <span className="ml-0.5 text-body font-semibold text-subtle">{stat.unit}</span>
                  )}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 프로젝트가 없을 때 Empty state (design-system 9.7) */}
      <section
        aria-labelledby="empty-title"
        className="flex flex-col items-center rounded-card border border-line bg-surface px-6 py-14 text-center"
      >
        <span className="flex size-[46px] items-center justify-center rounded-[13px] bg-primary-soft text-primary">
          <Icon name="folder" size={22} />
        </span>
        <h2 id="empty-title" className="mt-4 text-subheading font-bold text-text">
          첫 프로젝트를 만들어보세요
        </h2>
        <p className="mt-1 text-caption text-subtle">
          PDF나 PPTX 자료를 올리면 핵심 개념을 뽑아 드려요.
        </p>
        <button type="button" className={buttonStyles("primary", "mt-5")}>
          <Icon name="plus" size={18} />
          새 프로젝트
        </button>
      </section>
    </div>
  );
}

"use client";

import { Icon, type IconName } from "@/components/icon";
import { type LearningStats } from "@/lib/api";

export function LearningOverview({ stats }: { stats: LearningStats }) {
  const cards: { icon: IconName; label: string; value: number | string; unit: string; detail: string; tone: string }[] = [
    { icon: "target", label: "전체 이해도", value: stats?.overall_score ?? "-", unit: stats?.overall_score != null ? "%" : "", detail: "학습한 모든 개념 기준", tone: "bg-[#f0fdf4] text-[#16a34a]" },
    { icon: "book", label: "학습 개념", value: stats?.learned_concepts ?? "-", unit: "개", detail: stats ? `이번 주 새로 학습한 개념 ${stats.new_concepts_this_week}개` : "불러오는 중", tone: "bg-[#eef2ff] text-[#6366f1]" },
    { icon: "clock", label: "학습 일수", value: stats?.study_days_last_30 ?? "-", unit: "일", detail: stats ? `최근 30일 · ${stats.consecutive_study_days}일 연속 학습` : "불러오는 중", tone: "bg-[#f5f3ff] text-[#8b5cf6]" },
  ];
  return (
    <section aria-labelledby="overview-title">
      <h2 id="overview-title" className="mb-4 text-heading font-bold text-text">학습 개요</h2>
      <div className="grid grid-cols-3 gap-3.5 max-[600px]:grid-cols-1">
        {cards.map((card) => <div key={card.label} className="flex items-center gap-3.5 rounded-card border border-line bg-surface p-5">
          <span className={`flex size-[38px] shrink-0 items-center justify-center rounded-[10px] ${card.tone}`}><Icon name={card.icon} size={20} /></span>
          <div>
            <p className="text-caption text-subtle">{card.label}</p>
            <p className="text-title-2 font-bold text-text">{card.value}<span className="ml-0.5 text-body font-semibold text-subtle">{card.unit}</span></p>
            <p className="text-caption text-subtle">{card.detail}</p>
          </div>
        </div>)}
      </div>
    </section>
  );
}

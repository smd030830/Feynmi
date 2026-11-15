import type { Metadata } from "next";
import { RecordsPanel } from "@/components/records-panel";

export const metadata: Metadata = { title: "학습기록 · Feynmi" };
export const instant = false;

export default function RecordsPage() {
  return (
    <div className="space-y-7">
      <header>
        <h1 className="text-title-1 font-bold text-text">학습기록</h1>
        <p className="mt-1 text-body-lg text-muted">설명한 개념과 결과를 다시 확인하세요.</p>
      </header>
      <RecordsPanel />
    </div>
  );
}

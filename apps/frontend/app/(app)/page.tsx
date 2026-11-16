import type { Metadata } from "next";
import { CurrentNickname } from "@/components/auth-guard";
import { GreetingEyebrow, TodayLabel } from "@/components/greeting";
import { HomeDashboard } from "@/components/home-dashboard";

export const metadata: Metadata = { title: "홈 · Feynmi" };

// AuthGuard가 브라우저에서 로그인 상태를 복원한 뒤에야 그리므로 서버 렌더로는 검증할 수 없다.
// (app) 아래 페이지마다 둔다 (레이아웃에 두면 하위 페이지에 적용되지 않는다).
export const instant = false;

export default function HomePage() {
  return (
    <div className="flex flex-col gap-9">
      {/* 인사 줄 */}
      <div className="flex items-end justify-between max-[600px]:flex-col max-[600px]:items-start max-[600px]:gap-3">
        <div>
          <GreetingEyebrow />
          <h1 className="mt-1 text-title-1 font-bold text-text">안녕하세요, <CurrentNickname />님</h1>
          <p className="text-body-lg text-muted">오늘은 무엇을 이해해볼까요?</p>
        </div>
        <TodayLabel />
      </div>

      <HomeDashboard />
    </div>
  );
}

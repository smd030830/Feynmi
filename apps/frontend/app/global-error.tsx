"use client";

import { FailureScreen } from "@/components/failure-screen";
import "./globals.css";

export default function GlobalError({ retry }: { error: unknown; retry: () => void }) {
  return (
    <html lang="ko">
      <body style={{ fontFamily: "system-ui, sans-serif" }}>
        <FailureScreen title="서비스 화면을 준비하지 못했어요" description="다시 시도하거나 홈에서 학습을 확인해주세요." onRetry={retry} />
      </body>
    </html>
  );
}

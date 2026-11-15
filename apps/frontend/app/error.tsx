"use client";

import { FailureScreen } from "@/components/failure-screen";

export default function ErrorPage({ retry }: { error: unknown; retry: () => void }) {
  return <FailureScreen title="화면을 불러오지 못했어요" description="잠시 후 다시 시도해주세요. 저장된 학습기록은 그대로 확인할 수 있어요." onRetry={retry} />;
}

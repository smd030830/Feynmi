"use client";

import { useSearchParams } from "next/navigation";

export function LogoutNotice() {
  const params = useSearchParams();
  if (params.get("notice") !== "logout-incomplete") return null;
  return (
    <p role="status" className="mt-5 rounded-control bg-warning-soft p-4 text-body text-warning">
      현재 기기에서 로그아웃했어요. 모든 기기 로그아웃의 외부 계정 처리를 확인하지 못했어요.
      필요하면 다시 로그인한 뒤 재시도해주세요.
    </p>
  );
}

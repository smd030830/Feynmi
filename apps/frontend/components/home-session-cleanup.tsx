"use client";

import { useEffect } from "react";
import { cleanupSessions } from "@/lib/api";

// 이탈 알림이 누락된 세션도 홈으로 돌아왔을 때 닫는다.
export function HomeSessionCleanup() {
  useEffect(() => {
    void cleanupSessions().catch(() => undefined);
  }, []);
  return null;
}

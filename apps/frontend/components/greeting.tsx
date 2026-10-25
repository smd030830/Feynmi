"use client";

import { useSyncExternalStore } from "react";

// 시간대 인사와 날짜는 브라우저 시각 기준이라 클라이언트에서 계산한다 (서버 렌더에서는 빈 값).
const subscribe = () => () => {};

function getGreeting(hour: number) {
  if (hour < 12) return "좋은 아침이에요";
  if (hour < 18) return "좋은 오후예요";
  return "좋은 저녁이에요";
}

export function GreetingEyebrow() {
  const text = useSyncExternalStore(
    subscribe,
    () => getGreeting(new Date().getHours()),
    () => "",
  );
  return <p className="min-h-[18px] text-eyebrow font-extrabold text-primary-strong">{text}</p>;
}

export function TodayLabel() {
  const text = useSyncExternalStore(
    subscribe,
    () =>
      new Intl.DateTimeFormat("ko-KR", {
        timeZone: "Asia/Seoul",
        month: "long",
        day: "numeric",
        weekday: "long",
      }).format(new Date()),
    () => "",
  );
  return <p className="min-h-[22px] text-body font-semibold text-subtle">{text}</p>;
}

import type { Metadata } from "next";
import { OnboardingView } from "./onboarding-view";

export const metadata: Metadata = { title: "닉네임 설정 · Feynmi" };

// design-system 9.6. 구글로 처음 로그인한 사용자의 닉네임 설정
export default function OnboardingPage() {
  return <OnboardingView />;
}

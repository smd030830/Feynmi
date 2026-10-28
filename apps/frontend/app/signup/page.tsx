import type { Metadata } from "next";
import { SignupFlow } from "./signup-flow";

export const metadata: Metadata = { title: "회원가입 · Feynmi" };

// design-system 9.4. 단계는 로그인 상태와 사용자 정보에서 정하므로 새로고침해도 이어진다.
export default function SignupPage() {
  return <SignupFlow />;
}

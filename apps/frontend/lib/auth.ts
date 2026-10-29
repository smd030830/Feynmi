import { FirebaseError } from "firebase/app";
import type { Me } from "@/lib/api";

// 로그인 이후 사용자가 가야 할 가입 단계. 다 마쳤으면 null (architecture.md 4.2).
// 이메일 미인증은 /signup ②, 닉네임 없음은 이메일 가입자면 /signup ③, 구글 가입자면 /onboarding이다.
export function nextAuthStep(me: Me): "/signup" | "/onboarding" | null {
  if (!me.email_verified) return "/signup";
  if (me.nickname) return null;
  return me.sign_in_provider === "password" ? "/signup" : "/onboarding";
}

// 사용자가 창을 닫거나 다른 창을 열어 취소한 경우. 오류로 보여주지 않는다.
const CANCELLED = new Set(["auth/popup-closed-by-user", "auth/cancelled-popup-request"]);

const MESSAGES: Record<string, string> = {
  "auth/invalid-credential": "이메일 또는 비밀번호가 올바르지 않습니다.",
  "auth/invalid-email": "이메일 형식이 올바르지 않습니다.",
  "auth/user-disabled": "사용할 수 없는 계정입니다.",
  "auth/too-many-requests": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
  "auth/network-request-failed": "네트워크 연결을 확인한 뒤 다시 시도해주세요.",
  "auth/email-already-in-use": "이미 가입된 이메일입니다. 로그인해주세요.",
  "auth/weak-password": "비밀번호는 6자 이상이어야 합니다.",
  "auth/popup-blocked": "로그인 창이 차단되었습니다. 팝업을 허용한 뒤 다시 시도해주세요.",
};

// Firebase 인증 오류를 화면에 보여줄 한국어 문구로 바꾼다. 취소면 null.
export function authErrorMessage(error: unknown) {
  const code = error instanceof FirebaseError ? error.code : "";
  if (CANCELLED.has(code)) return null;
  return MESSAGES[code] ?? "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

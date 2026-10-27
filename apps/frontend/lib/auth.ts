import { FirebaseError } from "firebase/app";
import { onAuthStateChanged, type User } from "firebase/auth";
import { useEffect, useState } from "react";
import { getFirebaseAuth } from "@/lib/firebase";

// undefined는 Firebase가 저장된 로그인 상태를 아직 복원하지 않았다는 뜻이다.
export function useAuthUser() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useEffect(() => onAuthStateChanged(getFirebaseAuth(), setUser), []);
  return user;
}

// 임시 닉네임. FM-011 사용자 연결 후 백엔드의 닉네임으로 교체한다.
export function temporaryNickname(user: User) {
  return user.displayName || user.email?.split("@")[0] || "학습자";
}

// 사용자가 창을 닫거나 다른 창을 열어 취소한 경우. 오류로 보여주지 않는다.
const CANCELLED = new Set(["auth/popup-closed-by-user", "auth/cancelled-popup-request"]);

const MESSAGES: Record<string, string> = {
  "auth/invalid-credential": "이메일 또는 비밀번호가 올바르지 않습니다.",
  "auth/invalid-email": "이메일 형식이 올바르지 않습니다.",
  "auth/user-disabled": "사용할 수 없는 계정입니다.",
  "auth/too-many-requests": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
  "auth/network-request-failed": "네트워크 연결을 확인한 뒤 다시 시도해주세요.",
  "auth/popup-blocked": "로그인 창이 차단되었습니다. 팝업을 허용한 뒤 다시 시도해주세요.",
};

// Firebase 인증 오류를 화면에 보여줄 한국어 문구로 바꾼다. 취소면 null.
export function authErrorMessage(error: unknown) {
  const code = error instanceof FirebaseError ? error.code : "";
  if (CANCELLED.has(code)) return null;
  return MESSAGES[code] ?? "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

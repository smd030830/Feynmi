"use client";

import type { User } from "firebase/auth";
import { useRouter } from "next/navigation";
import { createContext, use, useEffect, type ReactNode } from "react";
import { temporaryNickname, useAuthUser } from "@/lib/auth";

const UserContext = createContext<User | null>(null);

// 로그인 이후 화면의 클라이언트 가드 (architecture.md 4.2). 실제 차단은 백엔드가 토큰으로 한다.
// TODO(FM-014): 이메일 미인증이면 /signup ② 단계, 닉네임이 없으면 ③ 단계나 /onboarding으로 보낸다.
export function AuthGuard({ children }: { children: ReactNode }) {
  const user = useAuthUser();
  const router = useRouter();

  useEffect(() => {
    if (user === null) router.replace("/login");
  }, [user, router]);

  // 로그인 상태를 복원하는 중이거나 /login으로 이동하는 중에는 보호된 화면을 그리지 않는다
  if (!user) return null;
  return <UserContext value={user}>{children}</UserContext>;
}

// 로그인하지 않은 사용자용 화면. 이미 로그인했거나 방금 로그인하면 홈으로 보낸다.
export function GuestOnly({ children }: { children: ReactNode }) {
  const user = useAuthUser();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  return children;
}

// AuthGuard 안에서만 쓴다
export function useCurrentUser() {
  const user = use(UserContext);
  if (!user) throw new Error("useCurrentUser는 AuthGuard 안에서만 쓸 수 있습니다.");
  return user;
}

export function CurrentNickname() {
  return temporaryNickname(useCurrentUser());
}

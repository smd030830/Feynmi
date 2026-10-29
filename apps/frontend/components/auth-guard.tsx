"use client";

import { signOut } from "firebase/auth";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { Button } from "@/components/button";
import { useAccount } from "@/components/account-provider";
import { nextAuthStep } from "@/lib/auth";
import { getFirebaseAuth } from "@/lib/firebase";

// 로그인 이후 화면의 클라이언트 가드 (architecture.md 4.2). 실제 차단은 백엔드가 토큰으로 한다.
// 로그인하지 않았으면 /login으로, 가입 단계가 남았으면 그 단계로 보낸다.
export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, me } = useAccount();
  const router = useRouter();
  const step = me ? nextAuthStep(me) : null;

  useEffect(() => {
    if (user === null) router.replace("/login");
    else if (step) router.replace(step);
  }, [user, step, router]);

  if (!user) return null;
  if (me === null) return <AccountLoadError />;
  // 불러오는 중이거나 가입 단계로 이동하는 중에는 보호된 화면을 그리지 않는다
  if (!me || step) return null;
  return children;
}

// 로그인하지 않은 사용자용 화면. 이미 로그인했거나 방금 로그인하면 홈으로 보낸다.
// 가입 단계가 남은 계정은 AuthGuard가 다시 해당 단계로 보낸다.
export function GuestOnly({ children }: { children: ReactNode }) {
  const { user } = useAccount();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  return children;
}

// 사용자 정보(GET /me)를 받지 못했을 때. 다시 시도하거나 로그아웃할 수 있다.
export function AccountLoadError() {
  const { retry } = useAccount();
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas px-10 text-center">
      <p className="text-body-lg text-muted">계정 정보를 불러오지 못했어요. 잠시 후 다시 시도해주세요.</p>
      <div className="flex gap-2">
        <Button onClick={retry}>다시 시도</Button>
        <Button variant="soft" onClick={() => void signOut(getFirebaseAuth())}>
          로그아웃
        </Button>
      </div>
    </main>
  );
}

// AuthGuard 안에서만 쓴다
export function useMe() {
  const { me } = useAccount();
  if (!me) throw new Error("useMe는 AuthGuard 안에서만 쓸 수 있습니다.");
  return me;
}

export function CurrentNickname() {
  return useMe().nickname;
}

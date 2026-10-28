"use client";

import { onAuthStateChanged, type User } from "firebase/auth";
import { createContext, use, useEffect, useState, type ReactNode } from "react";
import { getMe, type Me } from "@/lib/api";
import { getFirebaseAuth } from "@/lib/firebase";

type Account = {
  // undefined: Firebase가 저장된 로그인 상태를 아직 복원하지 않음, null: 로그아웃 상태
  user: User | null | undefined;
  // undefined: 불러오는 중, null: 불러오지 못함. 로그인하지 않았으면 항상 undefined
  me: Me | null | undefined;
  setMe: (me: Me) => void;
  // 이메일 인증 직후처럼 서버가 보는 토큰 클레임을 갱신한 뒤 사용자 정보를 다시 받는다
  refresh: () => Promise<Me>;
  retry: () => void;
};

const AccountContext = createContext<Account | null>(null);

// Firebase 로그인 상태와 백엔드의 사용자 정보(GET /me)를 앱 전체에서 한 번만 가져온다.
export function AccountProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  // 사용자가 바뀌면 이전 사용자의 정보를 쓰지 않도록 uid와 함께 보관한다
  const [loaded, setLoaded] = useState<{ uid: string; me: Me | null } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const uid = user?.uid;

  useEffect(() => onAuthStateChanged(getFirebaseAuth(), setUser), []);

  useEffect(() => {
    if (!uid) return;
    let cancelled = false;
    getMe().then(
      (me) => !cancelled && setLoaded({ uid, me }),
      () => !cancelled && setLoaded({ uid, me: null }),
    );
    return () => {
      cancelled = true;
    };
  }, [uid, attempt]);

  const account: Account = {
    user,
    me: uid && loaded?.uid === uid ? loaded.me : undefined,
    setMe: (me) => uid && setLoaded({ uid, me }),
    async refresh() {
      if (!user) throw new Error("로그인하지 않았습니다.");
      await user.reload();
      const me = await getMe(true);
      setLoaded({ uid: user.uid, me });
      return me;
    },
    retry() {
      setLoaded(null);
      setAttempt((value) => value + 1);
    },
  };
  return <AccountContext value={account}>{children}</AccountContext>;
}

export function useAccount() {
  const account = use(AccountContext);
  if (!account) throw new Error("useAccount는 AccountProvider 안에서만 쓸 수 있습니다.");
  return account;
}

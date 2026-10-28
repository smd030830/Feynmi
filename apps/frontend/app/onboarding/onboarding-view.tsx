"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAccount } from "@/components/account-provider";
import { AuthCard } from "@/components/auth-card";
import { AccountLoadError } from "@/components/auth-guard";
import { GoogleIcon } from "@/components/icon";
import { NicknameForm } from "@/components/nickname-form";
import { nextAuthStep } from "@/lib/auth";

const MAX_NICKNAME_LENGTH = 20;

export function OnboardingView() {
  const { user, me } = useAccount();
  const router = useRouter();
  const step = me ? nextAuthStep(me) : undefined;

  useEffect(() => {
    if (user === null) router.replace("/login");
    else if (step !== undefined && step !== "/onboarding") router.replace(step ?? "/");
  }, [user, step, router]);

  if (!user) return null;
  if (me === null) return <AccountLoadError />;
  if (!me || step !== "/onboarding") return null;

  const initial = (user.displayName || me.email).charAt(0).toUpperCase();
  return (
    <AuthCard eyebrow="WELCOME TO FEYNMI">
      <div className="flex flex-col items-center text-center">
        <span className="flex size-[72px] items-center justify-center rounded-full bg-[conic-gradient(#6366f1,#a78bfa,#38bdf8,#6366f1)] p-[3px]">
          <span className="flex size-full items-center justify-center rounded-full bg-surface text-title-3 font-bold text-primary-strong">
            {initial}
          </span>
        </span>
        <h2 className="mt-4 text-heading font-bold text-text">환영합니다! 닉네임을 정해주세요.</h2>
      </div>

      <div className="mt-6 flex items-center gap-3 rounded-control border border-line bg-canvas px-3.5 py-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[#f1f5ff]">
          <GoogleIcon />
        </span>
        <div className="min-w-0">
          <p className="text-micro text-subtle">연결된 계정</p>
          <p className="truncate text-body font-semibold text-text">{me.email}</p>
        </div>
      </div>

      <div className="mt-6">
        <NicknameForm initialNickname={(user.displayName ?? "").slice(0, MAX_NICKNAME_LENGTH)} />
      </div>
    </AuthCard>
  );
}

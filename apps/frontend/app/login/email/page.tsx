import type { Metadata } from "next";
import { AuthCard } from "@/components/auth-card";
import { GuestOnly } from "@/components/auth-guard";
import { EmailLoginForm } from "./email-login-form";

export const metadata: Metadata = { title: "이메일로 로그인 · Feynmi" };

// design-system 9.3
// TODO(FM-014): 이메일 미인증 계정으로 로그인하면 /signup ② 단계로 보낸다 (FR-4.1).
export default function EmailLoginPage() {
  return (
    <GuestOnly>
      <AuthCard eyebrow="이메일로 로그인">
        <EmailLoginForm />
      </AuthCard>
    </GuestOnly>
  );
}

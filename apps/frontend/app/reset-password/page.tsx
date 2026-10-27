import type { Metadata } from "next";
import { AuthCard } from "@/components/auth-card";
import { GuestOnly } from "@/components/auth-guard";
import { ResetPasswordForm } from "./reset-password-form";

export const metadata: Metadata = { title: "비밀번호 재설정 · Feynmi" };

// design-system 9.5
export default function ResetPasswordPage() {
  return (
    <GuestOnly>
      <AuthCard eyebrow="비밀번호 재설정">
        <ResetPasswordForm />
      </AuthCard>
    </GuestOnly>
  );
}

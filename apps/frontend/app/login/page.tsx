import type { Metadata } from "next";
import Link from "next/link";
import { AuthSplit } from "@/components/auth-split";
import { GuestOnly } from "@/components/auth-guard";
import { EmailLoginForm } from "./email-login-form";
import { GoogleLoginButton } from "./google-login-button";

export const metadata: Metadata = { title: "로그인 · Feynmi" };

export default function LoginPage() {
  return (
    <GuestOnly>
      <AuthSplit>
            <h2 className="text-title-1 font-bold text-text">
              Feynmi에 오신 것을
              <br />
              환영합니다.
            </h2>
  
            <div className="mt-10 flex flex-col gap-3">
              <GoogleLoginButton />
  
              <div className="flex items-center gap-3 py-1 text-caption text-subtle">
                <span className="h-px flex-1 bg-line" />
                또는
                <span className="h-px flex-1 bg-line" />
              </div>
  
              <EmailLoginForm />
            </div>
  
            <p className="mt-8 text-caption text-subtle">
              계속하면{" "}
              <Link href="/terms" className="font-semibold text-primary-strong underline-offset-2 hover:underline">
                이용약관
              </Link>
              과{" "}
              <Link href="/privacy" className="font-semibold text-primary-strong underline-offset-2 hover:underline">
                개인정보 처리방침
              </Link>
              에 동의하는 것으로 봅니다.
            </p>
      </AuthSplit>
    </GuestOnly>
  );
}

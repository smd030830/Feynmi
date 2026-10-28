import type { Metadata } from "next";
import Link from "next/link";
import { GuestOnly } from "@/components/auth-guard";
import { Icon, type IconName } from "@/components/icon";
import { Logo } from "@/components/logo";
import { EmailLoginForm } from "./email-login-form";
import { GoogleLoginButton } from "./google-login-button";

export const metadata: Metadata = { title: "로그인 · Feynmi" };

// 학습 흐름 (design-system 7.1): 개념 indigo, 설명 lavender, 질문 cyan, 이해 green
const flow: { icon: IconName; label: string; tone: string }[] = [
  { icon: "book", label: "개념", tone: "bg-[#eef2ff] text-[#6366f1]" },
  { icon: "brain", label: "설명", tone: "bg-[#f5f3ff] text-[#8b5cf6]" },
  { icon: "spark", label: "질문", tone: "bg-[#ecfeff] text-[#0891b2]" },
  { icon: "target", label: "이해", tone: "bg-[#f0fdf4] text-[#16a34a]" },
];

export default function LoginPage() {
  return (
    <GuestOnly>
      <main className="grid min-h-screen grid-cols-[56fr_44fr]">
        <BrandPanel />
        <section className="flex items-center justify-center bg-surface px-10 py-16">
          <div className="w-full max-w-[390px]">
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
          </div>
        </section>
      </main>
    </GuestOnly>
  );
}

function BrandPanel() {
  return (
    <section className="relative flex flex-col justify-between overflow-hidden bg-[linear-gradient(145deg,#f2f5ff_0%,#f8f5ff_56%,#f0fbff_100%)] px-16 py-14">
      {/* 장식 원 */}
      <span
        aria-hidden
        className="absolute -right-24 -top-24 size-[360px] rounded-full bg-[rgba(167,139,250,.12)]"
      />
      <span
        aria-hidden
        className="absolute -bottom-28 -left-20 size-[320px] rounded-full bg-[rgba(125,211,252,.15)]"
      />

      <div className="relative">
        <Logo />
      </div>

      <div className="relative">
        <p className="text-eyebrow font-extrabold uppercase text-primary-strong">
          Learn by explaining
        </p>
        <h1 className="mt-4 text-display font-bold text-text">
          알고 있다고 생각한 것을,
          <br />
          <em className="not-italic text-heading-accent">직접 설명해보세요.</em>
        </h1>

        <ol className="mt-12 flex items-center gap-3" aria-label="학습 흐름">
          {flow.map((step, index) => (
            <li key={step.label} className="flex items-center gap-3">
              <div className="flex flex-col items-center gap-2">
                <span
                  className={`flex size-14 items-center justify-center rounded-2xl shadow-brand-sm ${step.tone}`}
                >
                  <Icon name={step.icon} size={24} />
                </span>
                <span className="text-micro font-bold text-muted">{step.label}</span>
              </div>
              {index < flow.length - 1 && (
                <Icon name="arrow" size={16} className="mb-6 text-placeholder" />
              )}
            </li>
          ))}
        </ol>
      </div>

      <p className="relative max-w-[420px] text-body-lg text-muted">
        “남에게 설명할 수 있어야 비로소 내 것이 됩니다.”
      </p>
    </section>
  );
}

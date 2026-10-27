import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";

// design-system 9.3~9.5 인증 단계 카드: 폭 480px, 모서리 22px, modal 그림자
export function AuthCard({ eyebrow, children }: { eyebrow: string; children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col bg-canvas px-10 py-8">
      <header>
        <Link href="/login" aria-label="로그인 화면으로">
          <Logo />
        </Link>
      </header>
      <div className="flex flex-1 items-center justify-center py-10">
        <section className="w-full max-w-[480px] rounded-hero border border-line bg-surface p-8 shadow-modal">
          <h1 className="text-eyebrow font-extrabold text-primary-strong">{eyebrow}</h1>
          <div className="mt-6">{children}</div>
        </section>
      </div>
    </main>
  );
}

import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";
import { LegalBackLink } from "@/components/legal-back-link";

export function LegalDocument({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="relative min-h-[var(--viewport-height)] overflow-hidden bg-canvas px-10 py-8">
      <span aria-hidden className="pointer-events-none absolute -right-24 -top-32 size-96 rounded-full bg-primary-soft" />
      <span aria-hidden className="pointer-events-none absolute -bottom-32 -left-24 size-80 rounded-full bg-primary-soft" />
      <header className="relative mx-auto flex max-w-[1000px] items-center justify-between">
        <Link href="/" aria-label="Feynmi 홈으로"><Logo /></Link>
        <LegalBackLink />
      </header>
      <article className="relative mx-auto my-10 max-w-[760px] space-y-8 rounded-hero border border-line bg-surface p-10 shadow-modal">
        <header className="border-b border-line pb-6">
          <h1 className="text-title-1 font-bold text-text">{title}</h1>
          <p className="mt-2 text-caption text-subtle">시행일: 2026년 11월 15일</p>
        </header>
        <div className="space-y-7 text-body-lg leading-relaxed text-muted">{children}</div>
        <nav aria-label="서비스 정책" className="flex gap-6 border-t border-line pt-6 text-caption font-semibold text-primary-strong">
          <Link href="/terms" className="hover:underline">이용약관</Link>
          <Link href="/privacy" className="hover:underline">개인정보 처리방침</Link>
        </nav>
      </article>
    </main>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-3"><h2 className="text-heading font-bold text-text">{title}</h2>{children}</section>;
}

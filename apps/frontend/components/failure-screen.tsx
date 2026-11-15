/* eslint-disable @next/next/no-html-link-for-pages -- Error recovery reloads the document even if the app router failed. */
import { Button, buttonStyles } from "@/components/button";
import { Icon } from "@/components/icon";
import { Logo } from "@/components/logo";

export function FailureScreen({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  return (
    <main className="flex min-h-[var(--viewport-height)] flex-col bg-canvas px-10 py-8">
      <a href="/" aria-label="Feynmi 홈으로"><Logo /></a>
      <section className="m-auto w-full max-w-[560px] rounded-hero border border-line bg-surface p-10 text-center shadow-modal">
        <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary"><Icon name="shield" size={28} /></span>
        <h1 className="mt-6 text-title-2 font-bold text-text">{title}</h1>
        <p className="mt-3 text-body-lg text-muted">{description}</p>
        <div className="mt-7 flex justify-center gap-3">
          {onRetry && <Button onClick={onRetry}>다시 시도</Button>}
          <a href="/" className={buttonStyles(onRetry ? "soft" : "primary")}>홈으로 돌아가기</a>
        </div>
      </section>
    </main>
  );
}

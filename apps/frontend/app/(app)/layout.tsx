import { AuthGuard } from "@/components/auth-guard";
import { MobileMenuButton, MobileNavProvider, Sidebar } from "@/components/sidebar";
import { TopBarTitle } from "@/components/top-bar-title";

// design-system 9.1: 사이드바 + 상단 바 + 본문
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGuard>
      <MobileNavProvider>
      <div className="flex min-h-[var(--viewport-height)]">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="app-topbar sticky top-0 z-10 flex h-[62px] items-center justify-between border-b border-line bg-white/80 px-[42px] backdrop-blur">
            <span className="flex items-center gap-1">
              <MobileMenuButton />
              <TopBarTitle />
            </span>
            <span className="flex items-center gap-2 text-caption font-semibold text-muted">
              <span className="size-[7px] rounded-full bg-success-icon ring-4 ring-success-soft" />
              오늘의 학습 준비 완료
            </span>
          </header>
          <main className="app-main mx-auto w-full max-w-[1220px] px-[42px] pb-[54px] pt-9">{children}</main>
        </div>
      </div>
      </MobileNavProvider>
    </AuthGuard>
  );
}

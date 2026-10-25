import { Sidebar } from "@/components/sidebar";

// 임시 사용자. FM-011 사용자 연결 후 실제 값으로 교체한다.
const TEMP_USER = { nickname: "admin", email: "admin@feynmi.com" };

// design-system 9.1: 사이드바 + 상단 바 + 본문
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-screen">
      <Sidebar {...TEMP_USER} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-[62px] items-center justify-between border-b border-line bg-white/80 px-[42px] backdrop-blur">
          <span className="text-caption font-bold text-subtle">홈</span>
          <span className="flex items-center gap-2 text-caption font-semibold text-muted">
            <span className="size-[7px] rounded-full bg-success-icon ring-4 ring-success-soft" />
            오늘의 학습 준비 완료
          </span>
        </header>
        <main className="mx-auto w-full max-w-[1220px] px-[42px] pb-[54px] pt-9">{children}</main>
      </div>
    </div>
  );
}

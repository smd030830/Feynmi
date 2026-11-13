"use client";

import { signOut } from "firebase/auth";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, use, useEffect, useState, type ReactNode } from "react";
import { useMe } from "@/components/auth-guard";
import { Icon, type IconName } from "@/components/icon";
import { Logo } from "@/components/logo";
import { getFirebaseAuth } from "@/lib/firebase";

// design-system 9.1 공통 레이아웃: 사이드바 236px
const nav: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "홈", icon: "home" },
  { href: "/projects", label: "프로젝트", icon: "folder" },
  { href: "/records", label: "학습기록", icon: "chart" },
  { href: "/settings", label: "설정", icon: "settings" },
];

// 모바일(좁은 화면)에서 사이드바를 드로어로 여닫는 상태. 넓은 화면에서는 쓰이지 않는다.
const MobileNavContext = createContext<{ open: boolean; setOpen: (open: boolean) => void } | null>(null);

export function MobileNavProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  // Esc로 닫기
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return <MobileNavContext value={{ open, setOpen }}>{children}</MobileNavContext>;
}

function useMobileNav() {
  const ctx = use(MobileNavContext);
  if (!ctx) throw new Error("MobileNavProvider 안에서만 쓸 수 있습니다.");
  return ctx;
}

// 상단 바의 메뉴 버튼. 좁은 화면에서만 보인다 (globals.css .app-menu-btn)
export function MobileMenuButton() {
  const { open, setOpen } = useMobileNav();
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label="메뉴 열기"
      aria-expanded={open}
      className="app-menu-btn rounded-lg text-muted"
    >
      <Icon name="menu" size={22} />
    </button>
  );
}

const DAYS = ["월", "화", "수", "목", "금", "토", "일"];

export function Sidebar() {
  const pathname = usePathname();
  const me = useMe();
  const nickname = me.nickname ?? "";
  const { open, setOpen } = useMobileNav();

  function logout() {
    // 로그아웃되면 AuthGuard가 /login으로 보낸다
    void signOut(getFirebaseAuth());
  }

  return (
    <>
    <div className="app-backdrop" data-open={open} onClick={() => setOpen(false)} aria-hidden />
    <aside
      data-open={open}
      className="app-sidebar sticky top-0 flex h-screen w-[236px] shrink-0 flex-col border-r border-line bg-surface px-5 pb-6 pt-[30px]"
    >
      <button
        type="button"
        onClick={() => setOpen(false)}
        aria-label="메뉴 닫기"
        className="app-menu-close rounded-lg text-subtle"
      >
        <Icon name="close" size={22} />
      </button>
      <div className="px-1">
        <Logo />
      </div>

      <nav className="mt-9 flex flex-col gap-1" aria-label="주 메뉴">
        {nav.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              onClick={() => setOpen(false)}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-body font-semibold transition duration-200 ${
                active
                  ? "bg-primary-soft text-primary-strong"
                  : "text-muted hover:bg-[#fafbff] hover:text-text"
              }`}
            >
              <Icon name={item.icon} size={18} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <section className="mt-auto rounded-2xl border border-line bg-canvas p-4" aria-label="이번 주 학습">
        <p className="text-body font-bold text-text">이번 주 학습</p>
        <p className="mt-0.5 text-micro text-subtle">목표 3일 중 0일</p>
        <ol className="mt-3 grid grid-cols-7 gap-1">
          {DAYS.map((day) => (
            <li
              key={day}
              className="flex h-7 items-center justify-center rounded-md bg-[#eef0f4] text-micro font-bold text-subtle"
            >
              {day}
            </li>
          ))}
        </ol>
      </section>

      <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
        <span className="flex size-[34px] shrink-0 items-center justify-center rounded-full bg-[linear-gradient(135deg,#dbeafe,#ddd6fe)] text-body font-bold text-primary-strong">
          {nickname.charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-body font-semibold text-text">{nickname}</p>
          <p className="truncate text-micro text-subtle">{me.email}</p>
        </div>
        <button
          type="button"
          onClick={logout}
          aria-label="로그아웃"
          title="로그아웃"
          className="rounded-lg p-1.5 text-subtle transition duration-200 hover:bg-primary-soft hover:text-primary-strong"
        >
          <Icon name="logout" size={18} />
        </button>
      </div>
    </aside>
    </>
  );
}

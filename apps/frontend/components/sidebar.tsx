"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon, type IconName } from "@/components/icon";
import { Logo } from "@/components/logo";
import { SESSION_COOKIE } from "@/lib/session";

// design-system 9.1 공통 레이아웃: 사이드바 236px
const nav: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "홈", icon: "home" },
  { href: "/projects", label: "프로젝트", icon: "folder" },
  { href: "/records", label: "학습기록", icon: "chart" },
  { href: "/settings", label: "설정", icon: "settings" },
];

const DAYS = ["월", "화", "수", "목", "금", "토", "일"];

export function Sidebar({ nickname, email }: { nickname: string; email: string }) {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    document.cookie = `${SESSION_COOKIE}=; path=/; max-age=0`;
    router.replace("/login");
  }

  return (
    <aside className="sticky top-0 flex h-screen w-[236px] shrink-0 flex-col border-r border-line bg-surface px-5 pb-6 pt-[30px]">
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
          <p className="truncate text-micro text-subtle">{email}</p>
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
  );
}

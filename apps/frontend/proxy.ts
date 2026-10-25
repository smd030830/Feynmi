import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

// 로그인 전에도 볼 수 있는 경로 (FR-4.1, FR-4.4)
const PUBLIC_PATHS = ["/login", "/signup", "/reset-password", "/onboarding", "/terms", "/privacy"];

// 쿠키 유무만 보는 낙관적 검사다. 실제 인증은 FM-011에서 백엔드가 토큰을 검증한다.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const loggedIn = request.cookies.has(SESSION_COOKIE);
  const isPublic = PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));

  if (!loggedIn && !isPublic) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (loggedIn && pathname.startsWith("/login")) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|ico)$).*)"],
};

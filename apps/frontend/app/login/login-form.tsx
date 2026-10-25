"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/button";
import { Input } from "@/components/input";
import { SESSION_COOKIE } from "@/lib/session";

// 임시 로그인(FM-010 Firebase 연동 전까지). 계정 정보가 클라이언트 번들에 노출되므로 연동 시 제거한다.
const TEMP_EMAIL = "admin@feynmi.com";
const TEMP_PASSWORD = "1234";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // 기본 제출을 막아 입력값이 URL로 새지 않게 한다. Firebase 연동 때 로그인 호출로 교체.
    event.preventDefault();
    if (email === TEMP_EMAIL && password === TEMP_PASSWORD) {
      document.cookie = `${SESSION_COOKIE}=temp-admin; path=/; samesite=lax`;
      router.replace("/");
    } else {
      setError("이메일 또는 비밀번호가 올바르지 않습니다.");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input
        label="이메일"
        icon="mail"
        type="email"
        name="email"
        autoComplete="email"
        placeholder="name@example.com"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
      />
      <Input
        label="비밀번호"
        icon="lock"
        type="password"
        name="password"
        autoComplete="current-password"
        placeholder="비밀번호를 입력하세요"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />

      {error && (
        <p role="alert" className="text-caption text-red-600">
          {error}
        </p>
      )}

      <Button type="submit" className="mt-2 h-12 w-full" disabled={!email || !password}>
        로그인
      </Button>

      <div className="flex items-center justify-between text-caption">
        <Link
          href="/reset-password"
          className="font-semibold text-primary-strong underline-offset-2 hover:underline"
        >
          비밀번호를 잊으셨나요?
        </Link>
        <span className="text-subtle">
          처음이신가요?{" "}
          <Link
            href="/signup"
            className="font-semibold text-primary-strong underline-offset-2 hover:underline"
          >
            회원가입
          </Link>
        </span>
      </div>
    </form>
  );
}

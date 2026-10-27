"use client";

import { signInWithEmailAndPassword } from "firebase/auth";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/button";
import { Input } from "@/components/input";
import { authErrorMessage } from "@/lib/auth";
import { getFirebaseAuth } from "@/lib/firebase";

export function EmailLoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // 기본 제출을 막아 입력값이 URL로 새지 않게 한다
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      // 로그인되면 GuestOnly가 홈으로 보낸다
      await signInWithEmailAndPassword(getFirebaseAuth(), email, password);
    } catch (err) {
      setError(authErrorMessage(err) ?? "");
      setPending(false);
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
        <p role="alert" className="text-caption text-danger">
          {error}
        </p>
      )}

      <Button type="submit" className="mt-2 h-12 w-full" disabled={!email || !password || pending}>
        {pending ? "로그인 중…" : "로그인"}
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

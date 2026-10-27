"use client";

import { sendPasswordResetEmail } from "firebase/auth";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button, buttonStyles } from "@/components/button";
import { Input } from "@/components/input";
import { authErrorMessage } from "@/lib/auth";
import { getFirebaseAuth } from "@/lib/firebase";

export function ResetPasswordForm() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await sendPasswordResetEmail(getFirebaseAuth(), email);
      setSent(true);
    } catch (err) {
      setError(authErrorMessage(err) ?? "");
    } finally {
      setPending(false);
    }
  }

  if (sent) {
    // Firebase 이메일 열거 보호가 켜져 있으면 가입되지 않은 주소도 성공으로 응답한다
    return (
      <div className="flex flex-col gap-6">
        <p className="text-body-lg text-muted">
          <strong className="font-semibold text-text">{email}</strong>로 가입된 계정이 있다면 재설정
          메일을 보냈어요. 메일의 링크에서 새 비밀번호를 정해주세요.
        </p>
        <Link href="/login/email" className={buttonStyles("primary", "h-12 w-full")}>
          로그인으로 돌아가기
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <p className="text-body text-muted">가입한 이메일을 입력하면 비밀번호 재설정 링크를 보내드려요.</p>
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

      {error && (
        <p role="alert" className="text-caption text-danger">
          {error}
        </p>
      )}

      <Button type="submit" className="mt-2 h-12 w-full" disabled={!email || pending}>
        {pending ? "보내는 중…" : "재설정 메일 보내기"}
      </Button>

      <Link
        href="/login/email"
        className="self-center text-caption font-semibold text-primary-strong underline-offset-2 hover:underline"
      >
        로그인으로 돌아가기
      </Link>
    </form>
  );
}

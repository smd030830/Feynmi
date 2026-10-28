"use client";

import { createUserWithEmailAndPassword, sendEmailVerification, signOut } from "firebase/auth";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useAccount } from "@/components/account-provider";
import { AccountLoadError } from "@/components/auth-guard";
import { AuthSplit } from "@/components/auth-split";
import { AuthProgress } from "@/components/auth-progress";
import { Button } from "@/components/button";
import { Icon } from "@/components/icon";
import { Input } from "@/components/input";
import { NicknameForm } from "@/components/nickname-form";
import { authErrorMessage, nextAuthStep } from "@/lib/auth";
import { getFirebaseAuth } from "@/lib/firebase";

const RESEND_WAIT_SECONDS = 60; // PRD FR-4.1

export function SignupFlow() {
  const { user, me } = useAccount();
  const router = useRouter();
  // 인증 메일을 마지막으로 보낸 시각. 재발송 대기를 세는 데 쓴다.
  const [sentAt, setSentAt] = useState<number | null>(null);
  const step = me ? nextAuthStep(me) : undefined;

  // 가입을 마쳤거나 구글 가입자라면 이 화면에 머물 이유가 없다
  useEffect(() => {
    if (step !== undefined && step !== "/signup") router.replace(step ?? "/");
  }, [step, router]);

  if (user === undefined) return null;
  if (user === null) {
    return (
      <SignupPanel backHref="/login">
        <AuthProgress current={0} />
        <EmailStep onSent={setSentAt} />
      </SignupPanel>
    );
  }
  if (me === null) return <AccountLoadError />;
  if (!me || step !== "/signup") return null;

  return (
    <SignupPanel>
      {me.email_verified ? (
        <>
          <AuthProgress current={2} />
          <NicknameForm />
        </>
      ) : (
        <>
          <AuthProgress current={1} />
          <VerifyStep email={me.email} sentAt={sentAt} onSent={setSentAt} />
        </>
      )}
      <p className="mt-6 text-center text-caption text-subtle">
        Feynmi는 꼭 필요한 정보만 안전하게 보관합니다.
      </p>
    </SignupPanel>
  );
}

// 로그인 화면과 같은 틀의 오른쪽 폼 영역 (design-system 9.2, 9.4)
function SignupPanel({ backHref, children }: { backHref?: string; children: ReactNode }) {
  return (
    <AuthSplit>
      {backHref && (
        <Link href={backHref} className="mb-6 inline-block text-body font-semibold text-muted hover:text-text">
          이전으로
        </Link>
      )}
      <h1 className="mb-6 text-title-1 font-bold text-text">회원가입</h1>
      {children}
    </AuthSplit>
  );
}

// ① 이메일, 비밀번호 입력 → 계정을 만들고 인증 메일을 보낸다
function EmailStep({ onSent }: { onSent: (sentAt: number) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (password !== confirm) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }
    setPending(true);
    setError("");
    try {
      // 계정이 만들어지면 로그인 상태가 되어 ② 단계로 넘어간다
      const { user } = await createUserWithEmailAndPassword(getFirebaseAuth(), email, password);
      await sendEmailVerification(user);
      onSent(Date.now());
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
        autoComplete="new-password"
        placeholder="6자 이상 입력하세요"
        minLength={6}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />
      <Input
        label="비밀번호 확인"
        icon="lock"
        type="password"
        name="password-confirm"
        autoComplete="new-password"
        placeholder="비밀번호를 한 번 더 입력하세요"
        value={confirm}
        onChange={(event) => setConfirm(event.target.value)}
        required
      />

      {error && (
        <p role="alert" className="text-caption text-danger">
          {error}
        </p>
      )}

      <Button
        type="submit"
        className="mt-2 h-12 w-full"
        disabled={!email || !password || !confirm || pending}
      >
        {pending ? "메일 보내는 중…" : "인증 메일 받기"}
      </Button>
    </form>
  );
}

// ② 메일의 링크로 인증한 뒤 "인증 완료했어요"로 상태를 다시 확인한다
function VerifyStep({
  email,
  sentAt,
  onSent,
}: {
  email: string;
  sentAt: number | null;
  onSent: (sentAt: number) => void;
}) {
  const { refresh } = useAccount();
  const [now, setNow] = useState(() => Date.now());
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const remaining = sentAt
    ? Math.max(0, Math.ceil((sentAt + RESEND_WAIT_SECONDS * 1000 - now) / 1000))
    : 0;

  async function resend() {
    const user = getFirebaseAuth().currentUser;
    if (!user) return;
    setError("");
    try {
      await sendEmailVerification(user);
      setNow(Date.now());
      onSent(Date.now());
    } catch (err) {
      setError(authErrorMessage(err) ?? "");
    }
  }

  async function check() {
    setPending(true);
    setError("");
    try {
      // 인증되었으면 사용자 정보가 바뀌어 ③ 단계로 넘어간다
      const me = await refresh();
      if (!me.email_verified) {
        setError("아직 인증되지 않았어요. 메일의 링크를 눌렀는지 확인해주세요.");
      }
    } catch {
      setError("인증 상태를 확인하지 못했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-center text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-primary-soft text-primary">
        <Icon name="shield" size={26} />
      </span>
      <h2 className="mt-4 text-heading font-bold text-text">이메일로 보낸 링크를 눌러 인증해주세요.</h2>
      <p className="mt-2 text-body text-muted">
        <strong className="font-semibold text-text">{email}</strong>
      </p>

      <p className="mt-6 text-caption text-subtle">
        메일이 오지 않았나요?{" "}
        <button
          type="button"
          onClick={resend}
          disabled={remaining > 0}
          className="font-semibold text-primary-strong underline-offset-2 enabled:hover:underline disabled:cursor-not-allowed disabled:text-placeholder"
        >
          {remaining > 0 ? `다시 보내기 (${remaining}초)` : "다시 보내기"}
        </button>
      </p>

      {error && (
        <p role="alert" className="mt-4 text-caption text-danger">
          {error}
        </p>
      )}

      <Button className="mt-6 h-12 w-full" onClick={check} disabled={pending}>
        {pending ? "확인 중…" : "인증 완료했어요"}
      </Button>
      <button
        type="button"
        onClick={() => void signOut(getFirebaseAuth())}
        className="mt-4 text-caption font-semibold text-subtle underline-offset-2 hover:underline"
      >
        다른 이메일로 가입하기
      </button>
    </div>
  );
}

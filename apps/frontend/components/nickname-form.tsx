"use client";

import { useState, type FormEvent } from "react";
import { useAccount } from "@/components/account-provider";
import { Button } from "@/components/button";
import { Input } from "@/components/input";
import { apiErrorMessage, updateProfile } from "@/lib/api";

const MAX_LENGTH = 20; // PRD FR-4.1

// 이메일 가입 ③ 단계와 구글 온보딩이 함께 쓰는 닉네임 입력 (design-system 9.4, 9.6)
// 저장하면 사용자 정보가 갱신되어 가입 단계 가드가 홈으로 보낸다.
export function NicknameForm({ initialNickname = "" }: { initialNickname?: string }) {
  const { setMe } = useAccount();
  const [nickname, setNickname] = useState(initialNickname);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const trimmed = nickname.trim();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      setMe(await updateProfile(trimmed));
    } catch (err) {
      setError(apiErrorMessage(err));
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input
        label="닉네임"
        name="nickname"
        autoComplete="nickname"
        placeholder="사용할 닉네임을 입력하세요"
        maxLength={MAX_LENGTH}
        value={nickname}
        onChange={(event) => setNickname(event.target.value)}
        required
      />
      <p className="-mt-2 flex justify-between text-caption text-subtle">
        <span>닉네임은 설정에서 언제든 변경할 수 있어요.</span>
        <span>
          {nickname.length}/{MAX_LENGTH}
        </span>
      </p>

      {error && (
        <p role="alert" className="text-caption text-danger">
          {error}
        </p>
      )}

      <Button type="submit" className="mt-2 h-12 w-full" disabled={!trimmed || pending}>
        {pending ? "저장 중…" : "Feynmi 시작하기"}
      </Button>
    </form>
  );
}

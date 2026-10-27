"use client";

import { GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import { useState } from "react";
import { Button, OutlineButtonContent } from "@/components/button";
import { GoogleIcon } from "@/components/icon";
import { authErrorMessage } from "@/lib/auth";
import { getFirebaseAuth } from "@/lib/firebase";

export function GoogleLoginButton() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function login() {
    setPending(true);
    setError("");
    try {
      // 로그인되면 GuestOnly가 홈으로 보낸다
      await signInWithPopup(getFirebaseAuth(), new GoogleAuthProvider());
    } catch (err) {
      setError(authErrorMessage(err) ?? "");
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button variant="outline" onClick={login} disabled={pending}>
        <OutlineButtonContent tile={<GoogleIcon />} tileClassName="bg-[#f1f5ff]">
          {pending ? "Google 로그인 중…" : "Google로 계속하기"}
        </OutlineButtonContent>
      </Button>
      {error && (
        <p role="alert" className="text-caption text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

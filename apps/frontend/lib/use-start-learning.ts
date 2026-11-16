"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import { apiErrorMessage, startSession } from "@/lib/api";

export function useStartLearning() {
  const router = useRouter();
  const request = useRef(false);
  const [creating, setCreating] = useState(false);
  const [navigating, startTransition] = useTransition();
  const [startError, setStartError] = useState("");

  async function begin(conceptId: string) {
    if (request.current || navigating) return;
    request.current = true;
    setCreating(true);
    setStartError("");
    try {
      const session = await startSession(conceptId);
      startTransition(() => router.push(`/sessions/${session.id}`));
    } catch (error) {
      setStartError(apiErrorMessage(error));
    } finally {
      request.current = false;
      setCreating(false);
    }
  }

  return { begin, starting: creating || navigating, startError };
}

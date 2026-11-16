import type { Metadata } from "next";
import { Suspense } from "react";
import { SessionView } from "./session-view";

export const metadata: Metadata = { title: "설명하며 학습하기 · Feynmi" };
export const instant = false;
export default function SessionPage() {
  return <Suspense><SessionView /></Suspense>;
}

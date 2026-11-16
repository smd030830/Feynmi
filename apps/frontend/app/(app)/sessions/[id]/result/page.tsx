import type { Metadata } from "next";
import { Suspense } from "react";
import { ResultView } from "./result-view";

export const metadata: Metadata = { title: "학습 결과 · Feynmi" };
export const instant = false;
export default function ResultPage() { return <Suspense><ResultView /></Suspense>; }

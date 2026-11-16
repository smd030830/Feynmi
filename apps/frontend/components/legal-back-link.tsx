"use client";

import Link from "next/link";
import { useAccount } from "@/components/account-provider";

export function LegalBackLink() {
  const { user } = useAccount();
  return <Link href={user ? "/settings" : "/login"} className="text-body font-semibold text-primary-strong hover:underline">돌아가기</Link>;
}

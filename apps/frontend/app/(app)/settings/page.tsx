import type { Metadata } from "next";
import { SettingsView } from "./settings-view";

export const metadata: Metadata = { title: "설정 · Feynmi" };
export const instant = false;
export default function SettingsPage() { return <SettingsView />; }

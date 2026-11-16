"use client";

import { signOut } from "firebase/auth";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useAccount } from "@/components/account-provider";
import { useMe } from "@/components/auth-guard";
import { Button, buttonStyles } from "@/components/button";
import { Input } from "@/components/input";
import { Modal } from "@/components/modal";
import { apiErrorMessage, deleteAccount, getLearningSettings, getLoginEvents, getMe, revokeSessions, saveLearningSettings, updateProfile, uploadAvatar, type LearningSettings, type LoginEvent } from "@/lib/api";
import { getFirebaseAuth } from "@/lib/firebase";

const sections = [["account", "계정"], ["security", "로그인 및 보안"], ["learning", "학습 설정"], ["service", "서비스"]];
type Dialog = "profile" | "logins" | "revoke" | "delete" | null;

export function SettingsView() {
  const me = useMe();
  const router = useRouter();
  const [settings, setSettings] = useState<LearningSettings>();
  const [events, setEvents] = useState<LoginEvent[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [confirm, setConfirm] = useState("");
  const nickname = me.nickname ?? "";

  useEffect(() => {
    let cancelled = false;
    Promise.all([getLearningSettings(), getLoginEvents()]).then(([value, logins]) => {
      if (!cancelled) { setSettings(value); setEvents(logins.items); setLoadError(""); }
    }, (err) => !cancelled && setLoadError(apiErrorMessage(err)));
    return () => { cancelled = true; };
  }, [attempt]);

  async function change(value: Partial<LearningSettings>) {
    if (!settings || saving) return;
    const previous = settings;
    setSettings({ ...settings, ...value }); setSaving(true); setError(""); setStatus("저장 중…");
    try { setSettings(await saveLearningSettings(value)); setStatus("방금 저장했어요."); window.dispatchEvent(new Event("learning-settings-changed")); }
    catch (err) { setSettings(previous); setStatus(""); setError(apiErrorMessage(err)); }
    finally { setSaving(false); }
  }
  function open(value: Dialog) { setDialog(value); setConfirm(""); setError(""); }
  async function logoutEverywhere() {
    setPending(true); setError("");
    try { await revokeSessions(); await signOut(getFirebaseAuth()); router.replace("/login"); }
    catch {
      // 서버의 로컬 토큰 폐기는 외부 서비스 호출보다 먼저 완료될 수 있다.
      try { await signOut(getFirebaseAuth()); router.replace("/login?notice=logout-incomplete"); }
      catch (err) { setError(apiErrorMessage(err)); setPending(false); }
    }
  }
  async function removeAccount() {
    if (confirm !== "탈퇴") return;
    setPending(true); setError("");
    try { await deleteAccount(); await signOut(getFirebaseAuth()); router.replace("/login"); }
    catch (err) { setError(apiErrorMessage(err)); setPending(false); }
  }
  return <div className="space-y-7">
    <header className="flex items-end justify-between"><div><p className="text-eyebrow font-bold text-primary-strong">MY FEYNMI</p><h1 className="mt-2 text-title-1 font-bold">설정</h1><p className="mt-1 text-body-lg text-muted">계정과 학습 환경을 관리하세요.</p></div><p role="status" aria-live="polite" className="text-caption text-subtle">{status || "변경사항은 자동으로 저장됩니다."}</p></header>
    <section className="flex items-center gap-6 rounded-card border border-line bg-surface p-7">
      <Avatar url={me.avatar_url} nickname={nickname} /><div className="flex-1"><p className="text-caption text-subtle">프로필</p><h2 className="mt-1 text-title-2 font-bold">{nickname}</h2><p className="text-body text-muted">{me.email}</p><div className="mt-3 flex gap-2"><Tag>{me.sign_in_provider === "google.com" ? "Google 연결됨" : "이메일 계정"}</Tag><Tag>{me.email_verified ? "이메일 인증 완료" : "이메일 미인증"}</Tag></div></div><Button variant="soft" onClick={() => open("profile")}>프로필 수정</Button>
    </section>
    {error && !dialog && <p role="alert" className="rounded-control bg-danger-soft p-4 text-body text-danger">{error}</p>}
    <div className="grid grid-cols-[190px_minmax(0,1fr)] items-start gap-7">
      <nav aria-label="설정 섹션" className="sticky top-24 flex flex-col gap-2">{sections.map(([id, title]) => <a key={id} href={`#${id}`} className="rounded-control px-4 py-3 text-body font-bold text-muted hover:bg-primary-soft hover:text-primary-strong">{title}</a>)}</nav>
      <div className="space-y-6">
        <Section id="account" title="계정"><Row title="프로필" description={nickname}><Button variant="soft" onClick={() => open("profile")}>수정</Button></Row><Row title="연결된 계정" description={me.sign_in_provider === "google.com" ? "Google 계정으로 로그인하고 있어요." : "이메일 계정으로 로그인하고 있어요."}><Tag>{me.sign_in_provider === "google.com" ? "Google" : "이메일"}</Tag></Row><Row title="이메일 인증 상태" description={me.email}><span className="text-body font-bold text-success">{me.email_verified ? "인증 완료" : "미인증"}</span></Row></Section>
        <Section id="security" title="로그인 및 보안"><Row title="로그인 기록" description={events[0] ? `최근 · ${events[0].client_summary}` : "최근 로그인 기록을 확인하세요."}><Button variant="soft" onClick={() => open("logins")}>기록 보기</Button></Row><Row title="모든 기기에서 로그아웃" description="현재 기기를 포함해 로그인한 모든 기기에서 로그아웃합니다."><Button variant="danger" onClick={() => open("revoke")}>로그아웃</Button></Row></Section>
        <Section id="learning" title="학습 설정">
          {loadError ? <div role="alert" className="py-4"><p className="text-body text-danger">{loadError}</p><Button className="mt-3" variant="soft" onClick={() => setAttempt((n) => n + 1)}>다시 불러오기</Button></div> : !settings ? <p aria-busy className="py-5 text-body text-subtle">설정을 불러오고 있어요…</p> : <>
            <Row title="AI 질문 난이도" description="추가 질문의 깊이만 달라지며, 판정 기준과 점수는 같습니다."><div className="flex rounded-control bg-canvas p-1" role="group" aria-label="AI 질문 난이도">{(["basic", "deep"] as const).map((depth) => <button type="button" key={depth} aria-pressed={settings.question_depth === depth} disabled={saving} onClick={() => void change({ question_depth: depth })} className={`rounded-lg px-4 py-2 text-body font-bold disabled:opacity-50 ${settings.question_depth === depth ? "bg-surface text-primary-strong shadow-brand-sm" : "text-subtle"}`}>{depth === "basic" ? "기본" : "깊이 있게"}</button>)}</div></Row>
            <Row title="학습 알림" description="홈에서 학습 목표와 복습 알림을 받습니다."><button type="button" role="switch" aria-label="학습 알림" aria-checked={settings.notifications_enabled} disabled={saving} onClick={() => void change({ notifications_enabled: !settings.notifications_enabled })} className={`relative h-7 w-12 rounded-full transition-colors disabled:opacity-50 ${settings.notifications_enabled ? "bg-primary" : "bg-placeholder"}`}><span className={`absolute top-1 size-5 rounded-full bg-surface transition-transform ${settings.notifications_enabled ? "left-1 translate-x-5" : "left-1"}`} /></button></Row>
            <Row title="학습 목표" description="이번 주에 학습할 목표 일수를 정하세요."><div className="flex items-center gap-4"><Button variant="soft" aria-label="주간 목표 일수 줄이기" disabled={saving || settings.weekly_goal_days <= 1} onClick={() => void change({ weekly_goal_days: settings.weekly_goal_days - 1 })}>−</Button><span className="min-w-12 text-center text-body font-bold">주 {settings.weekly_goal_days}일</span><Button variant="soft" aria-label="주간 목표 일수 늘리기" disabled={saving || settings.weekly_goal_days >= 7} onClick={() => void change({ weekly_goal_days: settings.weekly_goal_days + 1 })}>＋</Button></div></Row>
          </>}
        </Section>
        <Section id="service" title="서비스"><Row title="이용약관"><Link href="/terms" className={buttonStyles("ghost")}>보기 ›</Link></Row><Row title="개인정보 처리방침"><Link href="/privacy" className={buttonStyles("ghost")}>보기 ›</Link></Row><Row title="회원 탈퇴" description="계정과 모든 학습 데이터를 삭제합니다."><Button variant="danger" onClick={() => open("delete")}>회원 탈퇴</Button></Row></Section>
        <div className="flex items-center justify-between"><p className="text-caption text-subtle">변경사항은 자동으로 저장됩니다.</p><Link href="/" className={buttonStyles("soft")}>대시보드로 돌아가기</Link></div>
      </div>
    </div>
    {dialog === "profile" && <ProfileDialog onClose={() => setDialog(null)} onSaved={() => setStatus("방금 저장했어요.")} />}
    {dialog === "logins" && <Modal title="최근 로그인 기록" onClose={() => setDialog(null)}><p className="mb-4 text-caption text-subtle">최근 10건의 로그인 기록입니다. IP 주소는 저장하지 않습니다.</p><ul className="divide-y divide-line">{events.map((event) => <li key={event.id} className="py-3"><p className="text-body font-semibold text-muted">{event.client_summary}</p><p className="mt-1 text-caption text-subtle">{new Date(event.occurred_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}</p></li>)}</ul>{!events.length && <p className="text-body text-subtle">아직 로그인 기록이 없어요.</p>}<Button className="mt-5 w-full" variant="soft" onClick={() => setDialog(null)}>닫기</Button></Modal>}
    {(dialog === "revoke" || dialog === "delete") && <Modal title={dialog === "delete" ? "정말 탈퇴하시겠어요?" : "모든 기기에서 로그아웃할까요?"} dismissible={false} onClose={() => !pending && setDialog(null)}>
      <p className="text-body-lg text-muted">{dialog === "delete" ? "탈퇴하면 모든 프로젝트, 자료, 학습기록이 즉시 삭제되며 복구할 수 없어요." : "현재 기기를 포함한 모든 기기에서 로그아웃됩니다. 다시 이용하려면 로그인해주세요."}</p>
      {dialog === "delete" && <Input className="mt-5" label="확인을 위해 ‘탈퇴’를 입력해주세요" value={confirm} onChange={(event) => setConfirm(event.target.value)} disabled={pending} autoComplete="off" />}
      {error && <p role="alert" className="mt-4 text-body text-danger">{error}</p>}
      <div className="mt-6 flex justify-end gap-2"><Button variant="ghost" disabled={pending} onClick={() => setDialog(null)}>취소</Button><Button variant="danger" disabled={pending || (dialog === "delete" && confirm !== "탈퇴")} onClick={() => void (dialog === "delete" ? removeAccount() : logoutEverywhere())}>{pending ? "처리 중…" : dialog === "delete" ? "탈퇴하기" : "모두 로그아웃"}</Button></div>
    </Modal>}
  </div>;
}

function ProfileDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const me = useMe();
  const { setMe } = useAccount();
  const [nickname, setNickname] = useState(me.nickname ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [retry, setRetry] = useState(0);
  const [savedNickname, setSavedNickname] = useState(me.nickname ?? "");
  const request = useRef(0);
  const mounted = useRef(true);
  const callbacks = useRef({ setMe, onSaved });
  const canClose = !saving && (!!error || !nickname.trim() || nickname.trim() === savedNickname);
  useEffect(() => { callbacks.current = { setMe, onSaved }; }, [setMe, onSaved]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const trimmed = nickname.trim();
    if (!trimmed || trimmed === savedNickname) return;
    const timeout = window.setTimeout(() => {
      const version = ++request.current;
      setSaving(true); setError(""); setStatus("저장 중…");
      void updateProfile(trimmed).then((value) => {
        if (!mounted.current || request.current !== version) return;
        setSavedNickname(trimmed); callbacks.current.setMe(value); setStatus("닉네임을 저장했어요."); callbacks.current.onSaved();
      }, (err) => { if (mounted.current && request.current === version) { setError(apiErrorMessage(err)); setStatus(""); } }).finally(() => { if (mounted.current && request.current === version) setSaving(false); });
    }, 600);
    return () => clearTimeout(timeout);
  }, [nickname, retry, savedNickname]);

  async function image(file?: File) {
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 2 * 1024 * 1024 || file.size === 0) { setError("JPG 또는 PNG 이미지를 2MB 이하로 선택해주세요."); return; }
    setSaving(true); setError(""); setStatus("이미지 저장 중…");
    try { await uploadAvatar(file); setMe(await getMe()); setStatus("프로필 이미지를 저장했어요."); onSaved(); }
    catch (err) { setError(apiErrorMessage(err)); setStatus(""); }
    finally { if (mounted.current) setSaving(false); }
  }
  return <Modal title="프로필 수정" onClose={() => canClose && onClose()} dismissible={false}>
    <div className="flex items-center gap-5"><Avatar url={me.avatar_url} nickname={me.nickname ?? ""} /><label className="cursor-pointer rounded-control bg-primary-soft px-4 py-3 text-body font-bold text-primary-strong">이미지 선택<input type="file" accept="image/jpeg,image/png" className="sr-only" disabled={saving || nickname.trim() !== savedNickname} onChange={(event) => { void image(event.target.files?.[0]); event.target.value = ""; }} /></label></div><p className="mt-3 text-caption text-subtle">JPG / PNG · 최대 2MB</p>
    <Input label="닉네임" className="mt-6" value={nickname} onChange={(event) => setNickname(event.target.value)} maxLength={20} disabled={saving} autoComplete="nickname" />
    <p className="mt-2 text-caption text-subtle">1~20자 · 입력을 마치면 자동으로 저장됩니다.</p>
    {!nickname.trim() && <p className="mt-2 text-caption text-danger">닉네임을 입력해주세요.</p>}
    {error && <div className="mt-3"><p role="alert" className="text-body text-danger">{error}</p>{nickname.trim() !== savedNickname && <Button className="mt-2" variant="soft" disabled={saving} onClick={() => setRetry((n) => n + 1)}>다시 저장</Button>}</div>}<p role="status" className="mt-3 min-h-5 text-caption text-subtle">{status}</p>
    <Button className="mt-5 w-full" variant="soft" disabled={!canClose} onClick={onClose}>닫기</Button>
  </Modal>;
}
function Avatar({ url, nickname }: { url: string | null; nickname: string }) {
  return <span className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary-soft text-title-1 font-bold text-primary-strong">{url ? <Image unoptimized src={url} alt="프로필" width={80} height={80} className="size-full object-cover" referrerPolicy="no-referrer" /> : nickname.charAt(0).toUpperCase()}</span>;
}
function Tag({ children }: { children: ReactNode }) { return <span className="rounded-full bg-primary-soft px-3 py-1 text-caption font-semibold text-primary-strong">{children}</span>; }
function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) { return <section id={id} className="scroll-mt-24 rounded-card border border-line bg-surface px-6"><h2 className="border-b border-line py-5 text-heading font-bold">{title}</h2><div className="divide-y divide-line">{children}</div></section>; }
function Row({ title, description, children }: { title: string; description?: string; children: ReactNode }) { return <div className="flex items-center justify-between gap-6 py-5"><div><h3 className="text-body font-bold text-muted">{title}</h3>{description && <p className="mt-1 text-caption text-subtle">{description}</p>}</div><div className="shrink-0">{children}</div></div>; }

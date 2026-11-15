"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { useAccount } from "@/components/account-provider";
import { Button } from "@/components/button";
import { Icon } from "@/components/icon";
import { Modal } from "@/components/modal";
import {
  apiErrorMessage,
  failureMessage,
  giveAiConsent,
  listMaterials,
  retryMaterial,
  uploadMaterial,
  type Material,
  type MaterialStatus,
} from "@/lib/api";

// 업로드 화면 (PRD FR-1.1, 1.7, 1.8). 형식·용량 검사는 서버가 한다(예외 시험을 위해 화면에서 미리 막지 않음).
const ACCEPT = ".pdf,.pptx,.png,.jpg,.jpeg,.heic,.heif,.txt,.docx,.hwp,.hwpx";
const POLL_MS = 2000;
const UPLOAD_PARALLEL = 3;
const IN_PROGRESS: MaterialStatus[] = ["pending_upload", "queued", "extracting", "generating_concepts"];

const STATUS_LABEL: Record<MaterialStatus, string> = {
  pending_upload: "업로드 중",
  queued: "분석 대기",
  extracting: "글자 추출 중",
  generating_concepts: "개념 생성 중",
  ready: "분석 완료",
  failed: "분석 실패",
};

type Notice = { id: number; name: string; message: string };

export function MaterialsPanel({
  projectId,
  projectName,
  onCountChange,
  onItemsChange,
}: {
  projectId: string;
  projectName: string;
  onCountChange: (count: number) => void;
  onItemsChange?: (items: Material[]) => void;
}) {
  const { me, setMe } = useAccount();
  const [items, setItems] = useState<Material[]>();
  const [loadError, setLoadError] = useState<unknown>();
  const [notices, setNotices] = useState<Notice[]>([]);
  const [uploading, setUploading] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null); // 동의를 기다리는 파일
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const { items } = await listMaterials(projectId);
      setItems(items);
      setLoadError(undefined);
      onCountChange(items.length);
      onItemsChange?.(items);
    } catch (error) {
      setLoadError(error);
    }
  }, [projectId, onCountChange, onItemsChange]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 분석 중인 자료가 있는 동안만 폴링한다 (architecture 4.2)
  const busy = items?.some((m) => IN_PROGRESS.includes(m.status)) ?? false;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [busy, refresh]);

  async function sendOne(file: File) {
    try {
      await uploadMaterial(projectId, file);
    } catch (error) {
      setNotices((list) => [
        { id: Date.now() + Math.random(), name: file.name, message: apiErrorMessage(error) },
        ...list,
      ]);
    } finally {
      setUploading((n) => n - 1);
    }
    await refresh();
  }

  // 파일마다 업로드 세 단계를 따로 실행하고, 동시에 올리는 수는 UPLOAD_PARALLEL개로 제한한다 (architecture 7.1)
  async function send(files: File[]) {
    setUploading((n) => n + files.length);
    const queue = [...files];
    const worker = async () => {
      for (let file = queue.shift(); file; file = queue.shift()) await sendOne(file);
    };
    await Promise.all(Array.from({ length: Math.min(UPLOAD_PARALLEL, files.length) }, worker));
  }

  function start(files: File[]) {
    if (files.length === 0) return;
    if (!me?.ai_consent_at) {
      setPendingFiles(files); // FR-1.8: 첫 업로드 때 동의를 받는다
      return;
    }
    void send(files);
  }

  async function consentAndSend() {
    const files = pendingFiles ?? [];
    setPendingFiles(null);
    try {
      setMe(await giveAiConsent());
      await send(files);
    } catch (error) {
      setNotices((list) => [{ id: Date.now(), name: "동의", message: apiErrorMessage(error) }, ...list]);
    }
  }

  async function retry(material: Material) {
    try {
      await retryMaterial(material.id);
    } catch (error) {
      setNotices((list) => [
        { id: Date.now(), name: material.title, message: apiErrorMessage(error) },
        ...list,
      ]);
    }
    await refresh();
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    start(Array.from(event.dataTransfer.files));
  }

  return (
    <section aria-labelledby="materials-title" className="flex flex-col gap-4">
      {/* 좁은 화면(600px 이하)에서는 제목과 업로드 버튼을 세로로 쌓는다 (팀 반응형 규칙과 같은 값) */}
      <div className="flex items-end justify-between max-[600px]:flex-col max-[600px]:items-start max-[600px]:gap-3">
        <div>
          <h2 id="materials-title" className="text-heading font-bold text-text">
            학습자료
          </h2>
          <p className="text-caption text-subtle">
            PDF · PPTX · 한글(HWP) · 워드 · TXT · 이미지 자료를 올리면 글자를 추출해 학습을 준비해요.
          </p>
        </div>
        <Button onClick={() => input.current?.click()} disabled={uploading > 0}>
          <Icon name="plus" size={18} />
          {uploading > 0 ? `올리는 중 (${uploading})` : "학습자료 업로드"}
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          aria-label="학습자료 파일 선택"
          onChange={(event) => {
            start(Array.from(event.target.files ?? []));
            event.target.value = ""; // 같은 파일을 다시 고를 수 있게 비운다
          }}
        />
      </div>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center rounded-card border-2 border-dashed px-6 py-8 text-center transition ${
          dragging ? "border-primary bg-primary-soft" : "border-line bg-surface"
        }`}
      >
        <span className="flex size-[46px] items-center justify-center rounded-[13px] bg-primary-soft text-primary">
          <Icon name="file" size={22} />
        </span>
        <p className="mt-3 text-body font-semibold text-text">여기에 파일을 끌어다 놓으세요</p>
        <p className="mt-1 text-caption text-subtle">
          PDF · PPTX · HWP · HWPX · DOCX · TXT · PNG · JPG · HEIC, 파일당 50MB, 300쪽/슬라이드까지. 여러 파일을 한 번에 올릴 수 있어요.
        </p>
      </div>

      {notices.length > 0 && (
        <ul aria-live="polite" className="flex flex-col gap-2">
          {notices.map((notice) => (
            <li
              key={notice.id}
              className="flex items-start justify-between gap-3 rounded-control bg-danger-soft px-4 py-3 text-caption text-danger"
            >
              <span>
                <b className="font-bold">{notice.name}</b> — {notice.message}
              </span>
              <button
                type="button"
                className="shrink-0 font-semibold"
                onClick={() => setNotices((list) => list.filter((n) => n.id !== notice.id))}
              >
                닫기
              </button>
            </li>
          ))}
        </ul>
      )}

      {loadError !== undefined && (
        <p className="text-caption text-danger">{apiErrorMessage(loadError)}</p>
      )}

      {items && items.length > 0 && (
        <ul className="flex flex-col divide-y divide-line rounded-card border border-line bg-surface">
          {items.map((m) => (
            <MaterialRow key={m.id} material={m} onRetry={retry} />
          ))}
        </ul>
      )}

      <p className="flex items-center gap-2 text-caption text-subtle">
        <Icon name="shield" size={16} className="text-placeholder" />
        업로드한 자료는 {projectName} 프로젝트의 개념 분석과 질문 생성에만 사용됩니다.
      </p>

      {pendingFiles && (
        <Modal title="외부 AI 전송 안내" onClose={() => setPendingFiles(null)}>
          <p className="text-body text-muted">
            자료 내용과 학습 답변이 외부 AI API(OpenAI)로 전송됩니다. 개념 추출, 그림 속 글자 읽기,
            답변 평가와 질문·피드백 생성에 사용됩니다. 설정에 따라 OpenRouter 중계를 거칠 수 있어요.
          </p>
          <p className="mt-3 text-caption text-subtle">불필요한 개인정보는 자료에서 지워 주세요. 자세한 처리 내용은 <a href="/privacy" target="_blank" rel="noopener noreferrer" className="font-semibold text-primary-strong underline">개인정보 처리방침 (새 창)</a>에서 확인할 수 있어요.</p>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPendingFiles(null)}>
              취소
            </Button>
            <Button onClick={() => void consentAndSend()}>동의하고 올리기</Button>
          </div>
        </Modal>
      )}

    </section>
  );
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function MaterialRow({
  material: m,
  onRetry,
}: {
  material: Material;
  onRetry: (m: Material) => void;
}) {
  const working = IN_PROGRESS.includes(m.status);
  const badge =
    m.status === "ready"
      ? "bg-success-soft text-success"
      : m.status === "failed"
        ? "bg-danger-soft text-danger"
        : "bg-primary-soft text-primary-strong";
  return (
    // 좁은 화면에서는 배지·버튼이 다음 줄로 내려간다
    <li className="flex items-center gap-4 px-5 py-4 max-[600px]:flex-wrap max-[600px]:gap-3 max-[600px]:px-4">
      {/* design-system 2장 팔레트: #f1f5f9 = 비활성 칩 (탭 개수 배지와 같은 값) */}
      <span className="flex size-10 shrink-0 items-center justify-center rounded-[11px] bg-[#f1f5f9] text-micro font-bold uppercase text-muted">
        {m.file_type}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-body font-semibold text-text">{m.title}</p>
        <p className="text-caption text-subtle">
          {formatSize(m.size_bytes)}
          {m.page_count !== null && ` · ${m.page_count}쪽`}
          {m.status === "ready" && ` · 개념 ${m.concept_count ?? 0}개`}
        </p>
        {m.status === "failed" && (
          <p className="mt-1 text-caption text-danger">
            {failureMessage(m.failure_code, m.file_type)} <span className="text-placeholder">({m.failure_code})</span>
          </p>
        )}
      </div>
      <span
        // design-system 8.2 Badge: caption 600, 여백 4px 8px, 모서리 99px, 의미색 글자 + 옅은 배경
        className={`flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1 text-caption font-semibold ${badge}`}
        aria-live="polite"
      >
        {working && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
        {STATUS_LABEL[m.status]}
      </span>
      {m.status === "failed" && (
        <Button variant="soft" onClick={() => onRetry(m)}>
          재시도
        </Button>
      )}
    </li>
  );
}

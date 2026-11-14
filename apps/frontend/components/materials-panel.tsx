"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { useAccount } from "@/components/account-provider";
import { Button } from "@/components/button";
import { Icon } from "@/components/icon";
import { Modal } from "@/components/modal";
import {
  apiErrorMessage,
  failureMessage,
  getMaterialPages,
  giveAiConsent,
  listMaterials,
  retryMaterial,
  uploadMaterial,
  type Material,
  type MaterialPage,
  type MaterialStatus,
} from "@/lib/api";

// 업로드 화면 (PRD FR-1.1, 1.7, 1.8). 형식·용량 검사는 서버가 한다(예외 시험을 위해 화면에서 미리 막지 않음).
const ACCEPT = ".pdf,.pptx,.png,.jpg,.jpeg";
const POLL_MS = 2000;
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
}: {
  projectId: string;
  projectName: string;
  onCountChange: (count: number) => void;
}) {
  const { me, setMe } = useAccount();
  const [items, setItems] = useState<Material[]>();
  const [loadError, setLoadError] = useState<unknown>();
  const [notices, setNotices] = useState<Notice[]>([]);
  const [uploading, setUploading] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null); // 동의를 기다리는 파일
  const [viewing, setViewing] = useState<Material | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const { items } = await listMaterials(projectId);
      setItems(items);
      setLoadError(undefined);
      onCountChange(items.length);
    } catch (error) {
      setLoadError(error);
    }
  }, [projectId, onCountChange]);

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

  async function send(files: File[]) {
    setUploading((n) => n + files.length);
    for (const file of files) {
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
            PDF · PPTX · PNG · JPG 자료를 올리면 글자를 추출해 학습을 준비해요.
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
          PDF · PPTX · PNG · JPG, 파일당 50MB, 300쪽/슬라이드까지. 여러 파일을 한 번에 올릴 수 있어요.
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
            <MaterialRow key={m.id} material={m} onRetry={retry} onView={setViewing} />
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
            자료가 외부 AI API(OpenAI)로 전송됩니다. 개념 분석과 질문 생성에만 사용되며, 본인만 볼 수
            있어요.
          </p>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPendingFiles(null)}>
              취소
            </Button>
            <Button onClick={() => void consentAndSend()}>동의하고 올리기</Button>
          </div>
        </Modal>
      )}

      {viewing && <PagesModal material={viewing} onClose={() => setViewing(null)} />}
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
  onView,
}: {
  material: Material;
  onRetry: (m: Material) => void;
  onView: (m: Material) => void;
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
          {m.status === "ready" && ` · DB 저장 조각 ${m.chunk_count}개`}
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
      {m.status === "ready" && (
        <Button variant="soft" onClick={() => onView(m)}>
          글자 보기
        </Button>
      )}
    </li>
  );
}

// 시연용: 뽑힌 쪽별 글자를 확인한다
function PagesModal({ material, onClose }: { material: Material; onClose: () => void }) {
  const [pages, setPages] = useState<MaterialPage[]>();
  const [error, setError] = useState<unknown>();

  useEffect(() => {
    let cancelled = false;
    getMaterialPages(material.id).then(
      (body) => !cancelled && setPages(body.pages),
      (err) => !cancelled && setError(err),
    );
    return () => {
      cancelled = true;
    };
  }, [material.id]);

  return (
    <Modal title={material.title} onClose={onClose}>
      <div className="max-h-[60vh] overflow-y-auto pr-1">
        {error !== undefined && <p className="text-caption text-danger">{apiErrorMessage(error)}</p>}
        {!pages && error === undefined && (
          <p className="text-caption text-subtle">글자를 불러오는 중이에요…</p>
        )}
        {pages?.map((page) => (
          <section key={page.number} className="border-b border-line py-3 last:border-0">
            <h3 className="text-micro font-bold text-primary-strong">{page.number}쪽</h3>
            <p className="mt-1 whitespace-pre-wrap text-caption text-text">
              {page.text || <span className="text-placeholder">(글자 없음)</span>}
            </p>
          </section>
        ))}
      </div>
      <div className="mt-5 flex justify-end">
        <Button variant="ghost" onClick={onClose}>
          닫기
        </Button>
      </div>
    </Modal>
  );
}

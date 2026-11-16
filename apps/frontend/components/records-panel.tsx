"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/button";
import { Icon } from "@/components/icon";
import { apiErrorMessage, listRecords, type RecordPage } from "@/lib/api";

const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric",
  hour: "2-digit", minute: "2-digit", hour12: false,
});

export function RecordsPanel({
  projectId,
  initialPage,
  onTotalChange,
}: {
  projectId?: string;
  initialPage?: RecordPage;
  onTotalChange?: (total: number) => void;
}) {
  const [loaded, setLoaded] = useState<{ scope?: string; page?: RecordPage; error?: string }>(
    { scope: projectId, page: initialPage },
  );
  const [attempt, setAttempt] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState("");
  const morePending = useRef(false);
  const generation = useRef(0);
  const current = loaded.scope === projectId ? loaded : undefined;
  const total = current?.page?.total;

  useEffect(() => {
    if (total !== undefined) onTotalChange?.(total);
  }, [total, onTotalChange]);

  useEffect(() => {
    const request = ++generation.current;
    if (initialPage && attempt === 0) return () => { generation.current = request + 1; };
    listRecords(projectId).then(
      (page) => { if (generation.current === request) setLoaded({ scope: projectId, page }); },
      (error) => { if (generation.current === request) setLoaded({ scope: projectId, error: apiErrorMessage(error) }); },
    );
    return () => { generation.current = request + 1; };
  }, [projectId, initialPage, attempt]);

  async function loadMore() {
    const cursor = current?.page?.next_cursor;
    if (!cursor || morePending.current) return;
    const request = generation.current;
    morePending.current = true;
    setLoadingMore(true);
    setMoreError("");
    try {
      const next = await listRecords(projectId, cursor);
      if (request !== generation.current) return;
      setLoaded((previous) => {
        if (previous.scope !== projectId || !previous.page) return previous;
        const known = new Set(previous.page.items.map((item) => item.id));
        return {
          scope: projectId,
          page: { ...next, items: [...previous.page.items, ...next.items.filter((item) => !known.has(item.id))] },
        };
      });
    } catch (error) {
      if (request === generation.current) setMoreError(apiErrorMessage(error));
    } finally {
      morePending.current = false;
      if (request === generation.current) setLoadingMore(false);
    }
  }

  return (
    <section className="space-y-5" aria-label="학습기록 목록" aria-busy={!current?.page && !current?.error}>
      {current?.error ? (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-control bg-danger-soft p-4">
          <p className="text-body text-danger">{current.error}</p>
          <Button variant="soft" onClick={() => setAttempt((value) => value + 1)}>다시 시도</Button>
        </div>
      ) : !current?.page ? (
        <p role="status" className="text-body text-subtle">학습기록을 불러오고 있어요…</p>
      ) : (
        <>
          <div className="flex justify-end">
            <span className="rounded-full bg-primary-soft px-4 py-2 text-caption font-bold text-primary-strong">총 {current.page.total}회 학습</span>
          </div>
          {current.page.items.length === 0 ? (
            <div className="flex flex-col items-center rounded-card border border-line bg-surface px-6 py-14 text-center">
              <Icon name="chart" size={28} className="text-primary" />
              <h2 className="mt-4 text-subheading font-bold text-text">아직 학습기록이 없어요</h2>
              <p className="mt-1 text-caption text-subtle">개념을 설명하고 나면 여기에서 다시 볼 수 있어요.</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {current.page.items.map((record) => {
                const completed = record.status === "completed";
                const minutes = Math.max(1, Math.ceil((Date.parse(record.ended_at ?? record.started_at) - Date.parse(record.started_at)) / 60000));
                return (
                  <li key={record.id}>
                    <Link href={`/sessions/${record.id}${completed ? "/result" : ""}`} className="flex items-center gap-5 rounded-card border border-line bg-surface p-5 transition hover:border-primary-line hover:shadow-brand-sm">
                      <span className={`flex size-10 shrink-0 items-center justify-center rounded-full ${completed ? "bg-success-soft text-success" : "bg-canvas text-subtle"}`}>
                        <Icon name={completed ? "check" : "clock"} size={20} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3">
                          <h2 className="truncate text-subheading font-bold text-text">{record.concept_title}</h2>
                          <span className="shrink-0 text-caption text-subtle">{completed ? "완료" : "중단"}</span>
                        </div>
                        <p className="mt-1 truncate text-caption text-subtle">
                          {record.project_name} · <time dateTime={record.started_at}>{dateFormat.format(new Date(record.started_at))}</time> · {minutes}분 학습
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-caption text-subtle">이해도</p>
                        <p className="text-heading font-bold text-text">{record.score === null ? "-" : `${record.score}%`}</p>
                      </div>
                      <Icon name="chevron" size={18} className="shrink-0 text-placeholder" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {moreError && <p role="alert" className="text-body text-danger">{moreError}</p>}
          {current.page.next_cursor && (
            <div className="flex justify-center">
              <Button variant="soft" disabled={loadingMore} onClick={() => void loadMore()}>
                {loadingMore ? "불러오는 중…" : moreError ? "다시 불러오기" : "더 보기"}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

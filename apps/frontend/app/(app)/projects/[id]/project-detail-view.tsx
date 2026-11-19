"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Button, buttonStyles } from "@/components/button";
import { Icon, type IconName } from "@/components/icon";
import { MaterialsPanel } from "@/components/materials-panel";
import { Modal } from "@/components/modal";
import { RecordsPanel } from "@/components/records-panel";
import { ProgressRing } from "@/components/progress-ring";
import { ProjectTile } from "@/components/project-tile";
import { StateDistributionBar } from "@/components/state-distribution-bar";
import { StateBadge } from "@/components/learning-feedback";
import { ApiError, apiErrorMessage, deleteProject, getProject, listConcepts, listRecords, listMaterials, type Concept, type Project, type RecordPage, type Material } from "@/lib/api";
import { useStartLearning } from "@/lib/use-start-learning";

const tabs = [
  { key: "concepts", label: "개념" },
  { key: "materials", label: "학습자료" },
  { key: "records", label: "학습기록" },
] as const;

type TabKey = (typeof tabs)[number]["key"];

function tabCount(project: Project, tab: TabKey, recordTotal?: number) {
  if (tab === "concepts") return Object.values(project.state_counts).reduce((a, b) => a + b, 0);
  if (tab === "materials") return project.material_count;
  return recordTotal ?? "-";
}

export function ProjectDetailView() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: TabKey = tabs.some((t) => t.key === tabParam) ? (tabParam as TabKey) : "concepts";

  // undefined: 불러오는 중
  const [loaded, setLoaded] = useState<{ id: string; project?: Project; concepts?: Concept[]; records?: RecordPage; materials?: Material[]; recordTotal?: number; recommendedId?: string; error?: unknown }>();
  const [attempt, setAttempt] = useState(0);
  const { begin, starting, startError } = useStartLearning();
  const [refreshError, setRefreshError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const deletePending = useRef(false);

  async function removeProject() {
    if (deletePending.current) return;
    deletePending.current = true;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteProject(id);
      setConfirmDelete(false);
      router.replace("/projects");
    } catch (error) {
      setDeleteError(error instanceof ApiError && error.code === "storage_unavailable"
        ? "원본 파일을 삭제하지 못했어요. 프로젝트는 유지되며 잠시 후 다시 삭제할 수 있어요."
        : apiErrorMessage(error));
    } finally {
      deletePending.current = false;
      setDeleting(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    // 기록 조회 실패는 기록 탭에서 재시도하고 프로젝트·자료 접근은 유지한다.
    Promise.all([getProject(id), listConcepts(id), listRecords(id).catch(() => undefined), listMaterials(id).catch(() => undefined)]).then(
      ([project, concepts, records, materials]) => !cancelled && setLoaded({ id, project, concepts: concepts.items, records, materials: materials?.items, recordTotal: records?.total, recommendedId: concepts.recommendation?.concept_id }),
      (error) => !cancelled && setLoaded({ id, error }),
    );
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const current = loaded?.id === id ? loaded : undefined;
  const concepts = current?.concepts ?? [];
  const nextConcept = concepts.find((concept) => concept.id === current?.recommendedId);
  // 자료를 올리면 탭과 머리글의 자료 수를 맞춘다
  const setMaterialCount = useCallback(
    (count: number) =>
      setLoaded((prev) =>
        prev?.id === id && prev.project && prev.project.material_count !== count
          ? { ...prev, project: { ...prev.project, material_count: count } }
          : prev,
      ),
    [id],
  );

  const setRecordTotal = useCallback((total: number) => {
    setLoaded((previous) => previous?.id === id && previous.recordTotal !== total
      ? { ...previous, recordTotal: total }
      : previous);
  }, [id]);

  const removeRecentRecord = useCallback((recordId: string) => {
    setLoaded((previous) => {
      if (previous?.id !== id || !previous.records) return previous;
      const items = previous.records.items.filter((record) => record.id !== recordId);
      if (items.length === previous.records.items.length) return previous;
      return { ...previous, records: { ...previous.records, items, total: previous.records.total - 1 } };
    });
  }, [id]);

  const setMaterials = useCallback((items: Material[]) => {
    setLoaded((previous) => previous?.id === id ? { ...previous, materials: items } : previous);
  }, [id]);
  const materials = current?.materials;
  const busyCount = materials?.filter((material) => ["pending_upload", "queued", "extracting", "generating_concepts"].includes(material.status)).length ?? 0;
  const revision = materials?.map((material) => `${material.id}:${material.status}:${material.concept_count}`).join("|");

  // 자료 탭은 MaterialsPanel이 폴링하고, 다른 탭은 여기서 분석 완료를 감지한다.
  useEffect(() => {
    if (!busyCount || tab === "materials") return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const value = await listMaterials(id); if (active) setMaterials(value.items); }
      catch (error) { if (active) setRefreshError(apiErrorMessage(error)); }
      if (active) timer = setTimeout(() => void poll(), 2000);
    }
    timer = setTimeout(() => void poll(), 2000);
    return () => { active = false; clearTimeout(timer); };
  }, [id, busyCount, tab, setMaterials]);

  useEffect(() => {
    if (revision === undefined) return;
    let active = true;
    Promise.all([getProject(id), listConcepts(id)]).then(([project, value]) => {
      if (active) {
        setLoaded((previous) => previous?.id === id ? { ...previous, project, concepts: value.items, recommendedId: value.recommendation?.concept_id } : previous);
        setRefreshError("");
      }
    }).catch((error) => { if (active) setRefreshError(apiErrorMessage(error)); });
    return () => { active = false; };
  }, [id, revision]);

  if (current?.error) {
    const notFound = current.error instanceof ApiError && current.error.code === "not_found";
    return (
      <EmptyState
        icon="folder"
        title={notFound ? "프로젝트를 찾을 수 없어요" : "프로젝트를 불러오지 못했어요"}
        description={notFound ? "삭제되었거나 접근할 수 없는 프로젝트예요." : apiErrorMessage(current.error)}
      >
        {notFound ? (
          <Link href="/projects" className={buttonStyles("primary", "mt-5")}>
            프로젝트 목록으로
          </Link>
        ) : (
          <Button
            className="mt-5"
            onClick={() => {
              setLoaded(undefined);
              setAttempt((value) => value + 1);
            }}
          >
            다시 시도
          </Button>
        )}
      </EmptyState>
    );
  }

  const project = current?.project;
  if (!project) {
    return <div aria-busy className="h-[188px] animate-pulse rounded-card bg-[#eef0f4]" />;
  }

  return (
    <div className="flex flex-col gap-7">
      <nav aria-label="브레드크럼" className="flex items-center gap-1.5 text-caption text-subtle">
        <Link href="/projects" className="font-semibold hover:text-primary-strong">
          프로젝트
        </Link>
        <Icon name="chevron" size={14} className="text-placeholder" />
        <span aria-current="page" className="truncate font-semibold text-muted">
          {project.name}
        </span>
      </nav>

      <header className="flex items-center gap-6 rounded-card border border-line bg-surface p-7 max-[600px]:flex-wrap max-[600px]:gap-4 max-[600px]:p-5">
        <ProjectTile name={project.name} color={project.color} size="lg" />
        <div className="min-w-0 flex-1">
          <p className="text-eyebrow font-extrabold uppercase text-primary-strong">
            Project · 자료 {project.material_count}개
          </p>
          <h1 className="mt-1 truncate text-title-1 font-bold text-text">{project.name}</h1>
          {project.description && (
            <p className="mt-0.5 whitespace-pre-line text-body-lg text-muted">{project.description}</p>
          )}
          <div className="mt-4 max-w-[420px]">
            <StateDistributionBar counts={project.state_counts} />
          </div>
          <Button variant="danger" className="mt-4" onClick={() => { setDeleteError(""); setConfirmDelete(true); }}>프로젝트 삭제</Button>
        </div>
        <div className="flex shrink-0 flex-col items-center gap-4 max-[600px]:w-full max-[600px]:flex-row max-[600px]:justify-between">
          <ProgressRing score={project.score} />
          <Button disabled={!nextConcept || starting} onClick={() => nextConcept && void begin(nextConcept.id)}>{starting ? "학습 준비 중…" : "학습 시작하기"}</Button>
        </div>
      </header>
      {confirmDelete && (
        <Modal title="프로젝트 삭제" dismissible={false} onClose={() => !deletePending.current && setConfirmDelete(false)}>
          <p className="break-words text-body font-semibold text-text">{project.name}</p>
          <p className="mt-3 text-body text-muted">프로젝트와 모든 학습자료·개념·원본 파일을 영구 삭제합니다. 답변이 있는 이전 설명과 결과는 학습기록에서 계속 볼 수 있어요. 삭제한 프로젝트는 복구할 수 없어요.</p>
          {deleteError && <p role="alert" className="mt-3 text-caption text-danger">{deleteError}</p>}
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" disabled={deleting} onClick={() => setConfirmDelete(false)}>취소</Button>
            <Button variant="danger" disabled={deleting} onClick={() => void removeProject()}>{deleting ? "삭제 중…" : "삭제하기"}</Button>
          </div>
        </Modal>
      )}
      {startError && <p role="alert" className="rounded-control bg-danger-soft p-4 text-body text-danger">{startError}</p>}

      <div>
        <div role="tablist" aria-label="프로젝트 탭" className="flex gap-[25px] border-b border-line max-[600px]:gap-4 max-[600px]:overflow-x-auto">
          {tabs.map((t) => {
            const active = t.key === tab;
            return (
              <Link
                key={t.key}
                href={`/projects/${project.id}?tab=${t.key}`}
                replace
                scroll={false}
                role="tab"
                aria-selected={active}
                className={`-mb-px flex items-center gap-2 border-b-2 pb-3 text-body font-bold transition duration-200 ${
                  active
                    ? "border-primary text-primary-strong"
                    : "border-transparent text-subtle hover:text-text"
                }`}
              >
                {t.label}
                <span
                  className={`flex h-5 min-w-[22px] items-center justify-center rounded-full px-1.5 text-micro font-bold ${
                    active ? "bg-primary-soft text-primary-strong" : "bg-[#f1f5f9] text-subtle"
                  }`}
                >
                  {tabCount(project, t.key, current.recordTotal)}
                </span>
              </Link>
            );
          })}
        </div>

        <div role="tabpanel" className="pt-6">
          {tab === "concepts" && (
            <div className="grid grid-cols-[minmax(0,1fr)_280px] items-start gap-6 max-[1024px]:grid-cols-1">
              <section aria-labelledby="concepts-title" className="min-w-0 space-y-4">
                <h2 id="concepts-title" className="text-heading font-bold text-text">개념 이해도</h2>
                {busyCount > 0 && <p role="status" className="rounded-control bg-primary-soft p-4 text-body font-semibold text-primary-strong">자료 {busyCount}개 분석 중 · 완료되면 개념 목록이 갱신돼요.</p>}
                {refreshError && <p role="alert" className="text-caption text-danger">{refreshError}</p>}
                {concepts.length > 0 ? concepts.map((concept) => (
                  <button key={concept.id} type="button" disabled={starting} onClick={() => void begin(concept.id)} className="flex w-full flex-wrap items-center gap-4 rounded-card border border-line bg-surface p-5 text-left hover:border-primary-line disabled:opacity-60 max-[600px]:gap-3 max-[600px]:p-4">
                    <span className="min-w-0 flex-1 max-[600px]:basis-full">
                      <span className="block text-caption text-subtle">{concept.material_title}</span>
                      <span role="heading" aria-level={3} className="mt-1 block text-subheading font-bold">{concept.title}</span>
                      <span className="mt-1 block text-caption text-muted">{concept.description}</span>
                    </span>
                    <StateBadge state={concept.state} />
                    <span className="min-w-12 text-right text-body font-bold text-muted">{concept.score === null ? "-" : `${concept.score}%`}</span>
                    <span className={buttonStyles("soft")}>{concept.state === "not_studied" ? "학습하기" : "다시 학습"}</span>
                  </button>
                )) : (
                  <EmptyState icon="book" title="아직 개념이 없어요" description="학습자료를 올리면 핵심 개념을 뽑아 드려요.">
                    <Link href={`/projects/${project.id}?tab=materials`} replace scroll={false} className={buttonStyles("primary", "mt-5")}>학습자료 올리러 가기</Link>
                  </EmptyState>
                )}
              </section>
              <aside className="space-y-5">
                <section aria-labelledby="latest-material-title" className="rounded-card border border-line bg-surface p-5">
                  <div className="flex items-center justify-between gap-3">
                    <h2 id="latest-material-title" className="text-subheading font-bold text-text">학습자료</h2>
                    <Link href={`/projects/${project.id}?tab=materials`} replace className="text-caption font-semibold text-primary-strong">학습자료 추가</Link>
                  </div>
                  {materials?.[0] ? <>
                    <p className="mt-4 break-words text-body font-semibold text-muted">{materials[0].title}</p>
                    <p className="mt-1 text-caption text-subtle">{new Date(materials[0].created_at).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" })}</p>
                    <dl className="mt-4 space-y-2 rounded-control bg-canvas p-3 text-caption">
                      <div className="flex justify-between gap-2"><dt>추출 개념</dt><dd className="font-bold">{materials[0].concept_count ?? 0}개</dd></div>
                      <div className="flex justify-between gap-2"><dt>채점 요소</dt><dd className="font-bold">{materials[0].element_count ?? 0}개</dd></div>
                    </dl>
                  </> : <p className="mt-4 text-caption text-subtle">아직 확인할 학습자료가 없어요.</p>}
                  <Link href={`/projects/${project.id}?tab=materials`} replace className={buttonStyles("soft", "mt-4 w-full")}>학습자료 살펴보기</Link>
                </section>
                <section aria-labelledby="recent-learning-title" className="rounded-card border border-line bg-surface p-5">
                  <div className="flex items-center justify-between">
                    <h2 id="recent-learning-title" className="text-subheading font-bold text-text">최근 학습</h2>
                    <Link href={`/projects/${project.id}?tab=records`} replace className="text-caption font-semibold text-primary-strong">전체 보기</Link>
                  </div>
                  {current.records?.items.length ? <ul className="mt-4 space-y-3">{current.records.items.slice(0, 3).map((record) => (
                    <li key={record.id}><Link href={`/sessions/${record.id}${record.status === "completed" ? "/result" : ""}`} className="block rounded-control p-2 hover:bg-primary-soft">
                      <p className="truncate text-body font-semibold text-text">{record.concept_title}</p>
                      <p className="mt-1 text-caption text-subtle">{new Date(record.started_at).toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul" })} · {record.score === null ? "-" : `${record.score}%`}</p>
                    </Link></li>
                  ))}</ul> : <p className="mt-4 text-caption text-subtle">아직 학습기록이 없어요.</p>}
                </section>
              </aside>
            </div>
          )}
          {tab === "materials" && (
            <MaterialsPanel
              key={project.id}
              projectId={project.id}
              projectName={project.name}
              onCountChange={setMaterialCount}
              onItemsChange={setMaterials}
            />
          )}
          {tab === "records" && (
            <RecordsPanel key={project.id} projectId={project.id} initialPage={current.records} onTotalChange={setRecordTotal} onRecordDeleted={removeRecentRecord} />
          )}
        </div>
      </div>
    </div>
  );
}

// design-system 8.2 Empty state
function EmptyState({
  icon,
  title,
  description,
  children,
}: {
  icon: IconName;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <section className="flex flex-col items-center rounded-card border border-line bg-surface px-6 py-14 text-center">
      <span className="flex size-[46px] items-center justify-center rounded-[13px] bg-primary-soft text-primary">
        <Icon name={icon} size={22} />
      </span>
      <h2 className="mt-4 text-subheading font-bold text-text">{title}</h2>
      <p className="mt-1 text-caption text-subtle">{description}</p>
      {children}
    </section>
  );
}

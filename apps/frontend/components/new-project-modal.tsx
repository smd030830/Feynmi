"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { Button, buttonStyles, type ButtonVariant } from "@/components/button";
import { Icon } from "@/components/icon";
import { Input } from "@/components/input";
import { Modal } from "@/components/modal";
import { ProjectTile } from "@/components/project-tile";
import { apiErrorMessage, createProject, listProjects, type ProjectColor } from "@/lib/api";

// 백엔드 api/projects.py의 길이 제한과 같게 둔다
const NAME_MAX_LENGTH = 40;
const DESCRIPTION_MAX_LENGTH = 200;

// design-system 9.8 새 프로젝트 모달. 만들면 프로젝트 상세의 학습자료 탭으로 이동한다.
// nextColor를 모르면(목록을 받지 않은 화면) 열 때 목록 API로 받아 온다.
export function NewProjectModal({
  nextColor,
  onClose,
}: {
  nextColor?: ProjectColor;
  onClose: () => void;
}) {
  const router = useRouter();
  const descriptionId = useId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [fetchedColor, setFetchedColor] = useState<ProjectColor>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const color = nextColor ?? fetchedColor;

  useEffect(() => {
    if (nextColor) return;
    let cancelled = false;
    // 미리보기용이라 실패해도 만들기는 막지 않는다
    listProjects().then(
      (list) => !cancelled && setFetchedColor(list.next_color),
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [nextColor]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const project = await createProject(name.trim(), description.trim());
      router.push(`/projects/${project.id}?tab=materials`);
    } catch (e) {
      setError(apiErrorMessage(e));
      setSubmitting(false);
    }
  }

  return (
    <Modal title="새 프로젝트" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-5">
        <div className="flex items-center gap-3.5 rounded-[10px] bg-canvas p-3.5">
          {color ? (
            <ProjectTile name={name || "?"} color={color} />
          ) : (
            <span className="size-[42px] shrink-0 rounded-[12px] bg-[#eef0f4]" aria-hidden />
          )}
          <div className="min-w-0">
            <p className="truncate text-body font-bold text-text">{name.trim() || "프로젝트 이름"}</p>
            <p className="text-micro text-subtle">색은 자동으로 정해져요</p>
          </div>
        </div>

        <Input
          label="이름"
          icon="folder"
          placeholder="예: 운영체제"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={NAME_MAX_LENGTH}
          required
          autoFocus
        />

        <div>
          <label htmlFor={descriptionId} className="mb-2 block text-body font-bold text-muted">
            설명 <span className="font-medium text-subtle">(선택)</span>
          </label>
          <textarea
            id={descriptionId}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={DESCRIPTION_MAX_LENGTH}
            rows={3}
            placeholder="어떤 내용을 공부하는 프로젝트인가요?"
            className="block w-full resize-none rounded-control border border-[#dce2ea] bg-surface px-3.5 py-3 text-body-lg text-text transition duration-200 ease-out placeholder:text-placeholder focus-visible:border-[#818cf8] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary-soft"
          />
        </div>

        {error && (
          <p role="alert" className="rounded-control bg-danger-soft px-3.5 py-2.5 text-body text-danger">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            취소
          </Button>
          <Button type="submit" disabled={submitting || !name.trim()}>
            {submitting ? "만드는 중…" : "만들기"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// 새 프로젝트 모달을 여는 버튼. 서버 컴포넌트 화면(홈)에서도 쓴다.
export function NewProjectButton({
  variant = "primary",
  className,
  children,
}: {
  variant?: ButtonVariant;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={buttonStyles(variant, className)} onClick={() => setOpen(true)}>
        <Icon name="plus" size={18} />
        {children}
      </button>
      {open && <NewProjectModal onClose={() => setOpen(false)} />}
    </>
  );
}

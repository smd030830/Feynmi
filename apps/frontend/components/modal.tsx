"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

// design-system 8.2 Modal. 네이티브 <dialog>로 포커스 가두기와 Esc 닫기를 처리한다.
// dismissible이 false면(위험 동작 모달) 바깥 클릭으로 닫지 않는다.
export function Modal({
  title,
  onClose,
  dismissible = true,
  children,
}: {
  title: string;
  onClose: () => void;
  dismissible?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      // 카드 바깥(배경 막)을 누르면 이벤트 대상이 dialog 자신이다
      onClick={(event) => dismissible && event.target === event.currentTarget && onClose()}
      className="m-auto w-[460px] max-w-[calc(100vw-32px)] rounded-[22px] bg-transparent p-0 shadow-modal backdrop:bg-[rgba(15,23,42,0.4)]"
    >
      <div className="rounded-[22px] bg-surface p-8">
        <h2 id={titleId} className="text-title-2 font-bold text-text">
          {title}
        </h2>
        <div className="mt-5">{children}</div>
      </div>
    </dialog>
  );
}

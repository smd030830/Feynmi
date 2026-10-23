import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon } from "@/components/icon";

// design-system 8.1 Button. Link 등에 같은 모양을 입힐 때는 buttonStyles를 쓴다.
const base =
  "inline-flex items-center justify-center gap-2 font-semibold transition duration-200 ease-out disabled:cursor-not-allowed disabled:opacity-50";

const variants = {
  primary:
    "rounded-control px-[18px] py-3 text-button font-bold text-white bg-[linear-gradient(135deg,#6366f1,#7c66ea)] shadow-button-primary hover:-translate-y-px hover:shadow-button-primary-hover disabled:hover:translate-y-0 disabled:hover:shadow-button-primary",
  soft: "rounded-control px-[18px] py-3 text-body font-semibold bg-primary-soft text-primary-strong",
  ghost: "rounded-control px-[18px] py-3 text-body font-semibold text-muted",
  outline:
    "h-12 w-full rounded-control border border-line bg-surface px-3.5 text-body font-semibold text-[#334155] hover:border-primary-line hover:bg-[#fafbff]",
  danger: "rounded-control px-[18px] py-3 text-body font-semibold bg-danger-soft text-danger",
} as const;

export type ButtonVariant = keyof typeof variants;

export function buttonStyles(variant: ButtonVariant = "primary", className = "") {
  return `${base} ${variants[variant]} ${className}`.trim();
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
};

export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  return <button type="button" className={buttonStyles(variant, className)} {...props} />;
}

// outline 버튼의 왼쪽 24px 아이콘 타일과 오른쪽 화살표 (design-system 8.1)
export function OutlineButtonContent({
  tile,
  tileClassName = "bg-primary-soft text-primary",
  withArrow = true,
  children,
}: {
  tile: ReactNode;
  tileClassName?: string;
  withArrow?: boolean;
  children: ReactNode;
}) {
  return (
    <>
      <span
        className={`flex size-6 shrink-0 items-center justify-center rounded-lg ${tileClassName}`}
      >
        {tile}
      </span>
      <span className="flex-1 text-left">{children}</span>
      {withArrow && <Icon name="arrow" size={16} className="text-placeholder" />}
    </>
  );
}

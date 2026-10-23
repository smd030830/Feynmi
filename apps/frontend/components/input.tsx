import { useId, type InputHTMLAttributes } from "react";
import { Icon, type IconName } from "@/components/icon";

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  icon?: IconName;
};

// design-system 8.1 Field label + Input: 높이 48px, 앞 아이콘, 포커스 시 테두리와 ring
export function Input({ label, icon, className, ...props }: InputProps) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-2 block text-body font-bold text-muted">
        {label}
      </label>
      <div className="group flex h-12 items-center gap-2.5 rounded-control border border-[#dce2ea] bg-surface px-3.5 transition duration-200 ease-out focus-within:border-[#818cf8] focus-within:ring-[3px] focus-within:ring-primary-soft">
        {icon && (
          <Icon
            name={icon}
            size={18}
            className="shrink-0 text-placeholder transition-colors duration-200 group-focus-within:text-primary"
          />
        )}
        <input
          id={id}
          className="h-full min-w-0 flex-1 bg-transparent text-body-lg text-text placeholder:text-placeholder focus-visible:outline-none"
          {...props}
        />
      </div>
    </div>
  );
}

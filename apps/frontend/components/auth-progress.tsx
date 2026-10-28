import { Icon } from "@/components/icon";

const STEPS = ["이메일", "인증", "프로필"];

// design-system 8장 Auth progress: Stepper와 같은 표현의 3단계. current는 0부터 센다.
export function AuthProgress({ current }: { current: 0 | 1 | 2 }) {
  return (
    <ol className="mb-8 flex items-center" aria-label="가입 단계">
      {STEPS.map((label, index) => {
        const state = index < current ? "done" : index === current ? "active" : "pending";
        return (
          <li
            key={label}
            aria-current={state === "active" ? "step" : undefined}
            className="flex flex-1 items-center last:flex-none"
          >
            <div className="flex items-center gap-2">
              <span
                className={`flex size-[26px] items-center justify-center rounded-full text-micro font-bold ${
                  state === "done"
                    ? "bg-success-soft text-success"
                    : state === "active"
                      ? "bg-primary text-white ring-4 ring-primary-soft"
                      : "bg-[#f1f5f9] text-subtle"
                }`}
              >
                {state === "done" ? <Icon name="check" size={14} /> : index + 1}
              </span>
              <span
                className={`text-caption font-semibold ${state === "pending" ? "text-subtle" : "text-text"}`}
              >
                {label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <span
                aria-hidden
                className={`mx-3 h-px flex-1 ${state === "done" ? "bg-primary-line" : "bg-line"}`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

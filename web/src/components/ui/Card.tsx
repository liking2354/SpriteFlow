import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  glass?: boolean;
}

export function Card({ children, className = "", title, subtitle, actions, glass }: Props) {
  return (
    <div
      className={`rounded-l border border-line ${glass ? "glass" : "bg-bg-1"} ${className}`}
    >
      {(title || subtitle || actions) && (
        <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-[var(--line-soft)]">
          <div>
            {title && <div className="text-[14px] font-semibold text-txt-0">{title}</div>}
            {subtitle && <div className="text-[11.5px] text-txt-2 mt-1">{subtitle}</div>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </div>
  );
}

import { useRef, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  glass?: boolean;
  /** 关闭顶部高光线 */
  noTopLine?: boolean;
  /** 关闭鼠标 spotlight */
  noSpotlight?: boolean;
}

export function Card({
  children,
  className = "",
  title,
  subtitle,
  actions,
  glass,
  noTopLine,
  noSpotlight,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);

  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (noSpotlight) return;
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
    el.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      className={`relative rounded-l border border-line ${
        glass ? "glass" : "bg-bg-1"
      } ${noSpotlight ? "" : "tech-spotlight"} ${
        noTopLine ? "" : "tech-top-line"
      } ${className}`}
      style={{
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.02) inset, 0 12px 32px rgba(0,0,0,0.25)",
      }}
    >
      {(title || subtitle || actions) && (
        <div className="relative z-[1] flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-[var(--line-soft)]">
          <div>
            {title && (
              <div className="text-[14px] font-semibold text-txt-0 tracking-[0.2px]">
                {title}
              </div>
            )}
            {subtitle && (
              <div className="text-[11.5px] text-txt-2 mt-1">{subtitle}</div>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className="relative z-[1] p-5">{children}</div>
    </div>
  );
}

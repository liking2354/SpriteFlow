import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  glow?: "green" | "red" | "amber" | "acc";
  onClick?: () => void;
}

export function Pill({ children, className = "", glow, onClick }: Props) {
  const glowColor: Record<NonNullable<Props["glow"]>, string> = {
    green: "var(--green)",
    red: "var(--red)",
    amber: "var(--amber)",
    acc: "var(--acc)",
  };
  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 h-7 rounded-full border border-line text-txt-1 text-[11px] hover:border-[#2f3647] hover:text-txt-0 transition-all glass ${
        onClick ? "cursor-pointer" : ""
      } ${className}`}
    >
      {glow && (
        <span className="relative inline-flex items-center justify-center">
          <span
            className="absolute w-3 h-3 rounded-full opacity-50 animate-pulse-glow"
            style={{ background: glowColor[glow], filter: "blur(3px)" }}
          />
          <span
            className="relative w-1.5 h-1.5 rounded-full"
            style={{
              background: glowColor[glow],
              boxShadow: `0 0 8px ${glowColor[glow]}`,
            }}
          />
        </span>
      )}
      <span className="relative z-[1]">{children}</span>
    </div>
  );
}

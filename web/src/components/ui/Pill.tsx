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
      className={`flex items-center gap-1.5 px-3 h-7 rounded-full bg-bg-3 border border-line text-txt-1 text-[11px] hover:border-[#2f3647] hover:text-txt-0 transition-colors ${onClick ? "cursor-pointer" : ""} ${className}`}
    >
      {glow && (
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{
            background: glowColor[glow],
            boxShadow: `0 0 8px ${glowColor[glow]}`,
          }}
        />
      )}
      {children}
    </div>
  );
}

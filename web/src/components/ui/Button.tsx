import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outline";
type Size = "xs" | "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  iconLeft?: ReactNode;
}

const sizeMap: Record<Size, string> = {
  xs: "h-6 px-2 text-[10px] gap-1 rounded-sm",
  sm: "h-7 px-3 text-[11px] gap-1.5",
  md: "h-9 px-4 text-[12px] gap-2",
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  iconLeft,
  className = "",
  disabled,
  children,
  ...rest
}: Props) {
  const base =
    "relative inline-flex items-center justify-center rounded-s font-semibold transition-all duration-150 select-none";

  const variantCls: Record<Variant, string> = {
    primary:
      "tech-energy-btn tech-shimmer text-white border-0 hover:-translate-y-px disabled:opacity-50 disabled:translate-y-0 disabled:saturate-50",
    ghost: "bg-transparent text-txt-1 hover:bg-bg-3 hover:text-txt-0",
    outline:
      "bg-bg-3 text-txt-1 border border-line hover:border-[#2f3647] hover:text-txt-0 tech-shimmer",
  };

  const styleByVariant =
    variant === "primary"
      ? {
          background:
            "linear-gradient(135deg, var(--acc), var(--acc-hover))",
          boxShadow:
            "0 4px 16px var(--acc-glow), inset 0 1px 0 rgba(255,255,255,0.15)",
        }
      : undefined;

  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`${base} ${sizeMap[size]} ${variantCls[variant]} ${className}`}
      style={styleByVariant}
    >
      {loading ? <span className="spinner" /> : iconLeft}
      <span className="relative z-[1]">{children}</span>
    </button>
  );
}

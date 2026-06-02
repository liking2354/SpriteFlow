import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outline";
type Size = "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  iconLeft?: ReactNode;
}

const sizeMap: Record<Size, string> = {
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
    "inline-flex items-center justify-center rounded-s font-semibold transition-all duration-150 select-none";

  const variantCls: Record<Variant, string> = {
    primary:
      "text-white border-0 shadow-[0_4px_16px_var(--acc-glow)] hover:-translate-y-px hover:shadow-[0_6px_22px_var(--acc-glow)] disabled:opacity-50 disabled:translate-y-0",
    ghost:
      "bg-transparent text-txt-1 hover:bg-bg-3 hover:text-txt-0",
    outline:
      "bg-bg-3 text-txt-1 border border-line hover:border-[#2f3647] hover:text-txt-0",
  };

  const styleByVariant =
    variant === "primary"
      ? { background: "linear-gradient(135deg, var(--acc), var(--acc-hover))" }
      : undefined;

  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`${base} ${sizeMap[size]} ${variantCls[variant]} ${className}`}
      style={styleByVariant}
    >
      {loading ? <span className="spinner" /> : iconLeft}
      {children}
    </button>
  );
}

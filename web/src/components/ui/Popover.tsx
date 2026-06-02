import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  trigger: ReactNode;          // 触发器（一个 button 元素）
  children: ReactNode | ((close: () => void) => ReactNode);
  placement?: "bottom-start" | "bottom-end" | "top-start" | "top-end";
  width?: number;
  className?: string;
  open?: boolean;              // 受控
  onOpenChange?: (open: boolean) => void;
}

export function Popover({
  trigger,
  children,
  placement = "bottom-start",
  width,
  className = "",
  open: controlledOpen,
  onOpenChange,
}: Props) {
  const [internal, setInternal] = useState(false);
  const open = controlledOpen ?? internal;
  const setOpen = (v: boolean) => {
    if (controlledOpen === undefined) setInternal(v);
    onOpenChange?.(v);
  };

  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const placementCls: Record<NonNullable<Props["placement"]>, string> = {
    "bottom-start": "top-full left-0 mt-1.5",
    "bottom-end": "top-full right-0 mt-1.5",
    "top-start": "bottom-full left-0 mb-1.5",
    "top-end": "bottom-full right-0 mb-1.5",
  };

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen(!open)}>{trigger}</div>
      {open && (
        <div
          className={`absolute z-50 ${placementCls[placement]} ${className}`}
          style={{ width }}
        >
          <div className="rounded-m border border-line bg-bg-2 shadow-[0_12px_40px_rgba(0,0,0,0.5)]">
            {typeof children === "function" ? children(() => setOpen(false)) : children}
          </div>
        </div>
      )}
    </div>
  );
}

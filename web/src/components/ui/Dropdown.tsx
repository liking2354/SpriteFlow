import { useState, useRef, useEffect, useCallback, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface DropdownOption {
  value: string;
  label: string;
  group?: string;
  icon?: string;
  disabled?: boolean;
}

interface DropdownProps {
  options: DropdownOption[];
  value?: string;
  placeholder?: string;
  className?: string;
  width?: number;
  maxHeight?: number;
  searchable?: boolean;
  onChange?: (value: string) => void;
}

/**
 * 通用 Dropdown 组件
 * 下拉菜单通过 Portal 渲染到 document.body，避免被父容器 overflow/z-index 裁剪
 */
export function Dropdown({
  options,
  value,
  placeholder = "请选择...",
  className = "",
  width = 200,
  maxHeight = 240,
  searchable = false,
  onChange,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [menuStyle, setMenuStyle] = useState<React.CSSProperties>({});
  const ref = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // 计算下拉菜单位置（基于触发器元素在 viewport 中的位置）
  const calcPosition = useCallback(() => {
    if (!triggerRef.current) return {};
    const rect = triggerRef.current.getBoundingClientRect();
    const menuHeight = Math.min(options.length * 32 + 16, maxHeight);
    const spaceBelow = window.innerHeight - rect.bottom;
    const dropUp = spaceBelow < menuHeight + 8 && rect.top > menuHeight + 8;

    return {
      position: "fixed" as const,
      zIndex: 9999,
      width: Math.max(width, rect.width),
      left: rect.left,
      ...(dropUp
        ? { bottom: window.innerHeight - rect.top + 4 }
        : { top: rect.bottom + 4 }),
    };
  }, [options.length, maxHeight, width]);

  // 打开时计算位置
  useEffect(() => {
    if (open) {
      setMenuStyle(calcPosition());
    }
  }, [open, calcPosition]);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (ref.current?.contains(target)) return;
      setOpen(false);
      setSearch("");
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setSearch("");
      }
    };
    const onScroll = (e: Event) => {
      const target = e.target as Node;
      // 滚动来源在触发器或菜单内部 → 忽略（例如下拉列表自身的滚动条）
      if (ref.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
      setSearch("");
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  // 打开时聚焦搜索框
  useEffect(() => {
    if (open && searchable && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open, searchable]);

  const selected = options.find((o) => o.value === value);
  const filtered = searchable && search
    ? options.filter((o) =>
        o.label.toLowerCase().includes(search.toLowerCase()) ||
        (o.group?.toLowerCase().includes(search.toLowerCase()))
      )
    : options;

  // 按 group 分组
  const grouped: { group?: string; items: DropdownOption[] }[] = [];
  for (const opt of filtered) {
    const last = grouped[grouped.length - 1];
    if (!last || last.group !== opt.group) {
      grouped.push({ group: opt.group, items: [opt] });
    } else {
      last.items.push(opt);
    }
  }

  const handleSelect = (val: string) => {
    onChange?.(val);
    setOpen(false);
    setSearch("");
  };

  return (
    <div ref={ref} className={`inline-block ${className}`}>
      {/* 触发器 */}
      <div
        ref={triggerRef}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 h-8 px-2.5 text-[11px] border rounded-s cursor-pointer select-none transition-colors w-full"
        style={{
          color: selected ? "var(--txt-0)" : "var(--txt-3)",
          background: "var(--bg-0)",
          borderColor: open ? "var(--acc)" : "var(--line)",
          boxShadow: open ? "0 0 0 2px var(--acc-soft)" : undefined,
        }}
      >
        <span className="flex-1 truncate text-left">
          {selected ? (
            <span className="flex items-center gap-1.5">
              {selected.icon && <span>{selected.icon}</span>}
              <span>{selected.label}</span>
            </span>
          ) : (
            placeholder
          )}
        </span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          style={{
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.15s ease",
            flexShrink: 0,
          }}
        >
          <path d="M3 3.5L5 5.5L7 3.5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />
        </svg>
      </div>

      {/* 下拉面板 — Portal 到 body 避免被节点裁剪 */}
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="rounded-m border shadow-[0_12px_40px_rgba(0,0,0,0.5)] overflow-hidden"
            style={{
              ...menuStyle,
              background: "var(--bg-2)",
              borderColor: "var(--line)",
            }}
          >
            {/* 搜索框 */}
            {searchable && (
              <div className="px-2 py-1.5 border-b" style={{ borderColor: "var(--line-soft)" }}>
                <input
                  ref={inputRef}
                  type="text"
                  className="w-full h-7 px-2 text-[11px] rounded-s outline-none"
                  style={{
                    background: "var(--bg-0)",
                    color: "var(--txt-0)",
                    border: "1px solid var(--line-soft)",
                  }}
                  placeholder="搜索..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") { setOpen(false); setSearch(""); }
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            )}

            {/* 选项列表 */}
            <div className="overflow-y-auto py-1" style={{ maxHeight }}>
              {grouped.length === 0 ? (
                <div className="px-3 py-2 text-[11px] text-center" style={{ color: "var(--txt-3)" }}>
                  无匹配结果
                </div>
              ) : (
                grouped.map((g, gi) => (
                  <div key={g.group ?? `_ungrouped_${gi}`}>
                    {g.group && (
                      <div className="px-3 py-1 text-[9px] font-semibold uppercase tracking-wider" style={{ color: "var(--txt-3)" }}>
                        {g.group}
                      </div>
                    )}
                    {g.items.map((opt) => (
                      <div
                        key={opt.value}
                        onClick={() => !opt.disabled && handleSelect(opt.value)}
                        className={`flex items-center gap-2 px-3 py-1.5 text-[11px] cursor-pointer transition-colors ${opt.disabled ? "opacity-40 cursor-not-allowed" : ""}`}
                        style={{
                          color: opt.value === value ? "var(--acc)" : "var(--txt-1)",
                          background: opt.value === value ? "var(--acc-soft)" : undefined,
                        }}
                        onMouseEnter={(e) => {
                          if (!opt.disabled && opt.value !== value) {
                            e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (opt.value !== value) {
                            e.currentTarget.style.background = "";
                          }
                        }}
                      >
                        {opt.icon && <span className="text-xs">{opt.icon}</span>}
                        <span className="flex-1 truncate">{opt.label}</span>
                        {opt.value === value && (
                          <svg width="12" height="12" viewBox="0 0 12 12" style={{ flexShrink: 0 }}>
                            <path d="M2.5 6L4.5 8L9.5 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </div>
                    ))}
                  </div>
                ))
              )}
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}

/**
 * 简化的下拉触发器（用于行内紧凑场景）
 */
export function DropdownButton({
  children,
  open,
  onClick,
  className = "",
}: {
  children: ReactNode;
  open?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-1.5 h-8 px-2.5 text-[11px] border rounded-s cursor-pointer select-none transition-colors ${className}`}
      style={{
        color: "var(--txt-1)",
        background: "var(--bg-0)",
        borderColor: open ? "var(--acc)" : "var(--line)",
        boxShadow: open ? "0 0 0 2px var(--acc-soft)" : undefined,
      }}
    >
      {children}
      <svg
        width="10" height="10" viewBox="0 0 10 10"
        style={{
          transform: open ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 0.15s ease",
          flexShrink: 0,
          marginLeft: "auto",
        }}
      >
        <path d="M3 3.5L5 5.5L7 3.5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />
      </svg>
    </div>
  );
}

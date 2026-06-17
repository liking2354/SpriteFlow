import { useState } from "react";

interface CollapsibleSectionProps {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

/**
 * 可折叠的分组区块，用于表单属性分组展示
 * - 支持默认展开/折叠
 * - 显示属性数量
 * - 带动画过渡
 */
export function CollapsibleSection({
  title,
  count,
  defaultOpen = true,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-lg border overflow-hidden" style={{ borderColor: "var(--line)" }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:brightness-110 transition"
        style={{ background: "var(--bg-2)" }}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold" style={{ color: "var(--txt-1)" }}>
            {title}
          </span>
          {count !== undefined && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
              style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
            >
              {count}
            </span>
          )}
        </div>
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            color: "var(--txt-3)",
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform 0.2s",
          }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <div
        className="overflow-hidden transition-all duration-200"
        style={{
          maxHeight: open ? "2000px" : "0px",
          opacity: open ? 1 : 0,
        }}
      >
        <div className="p-3">{children}</div>
      </div>
    </div>
  );
}

/**
 * 将扁平属性列表按 ui:group 分组
 * @param schema 扁平的 properties 字典: { key: { type, title, "ui:group"?, ... } }
 * @returns 有序的分组映射 Map<groupName, [key, propDef][]>
 */
export function groupPropertiesByUiGroup<T = unknown>(
  schema: Record<string, T>,
): Map<string, [string, T][]> {
  const groups = new Map<string, [string, T][]>();

  for (const [key, prop] of Object.entries(schema)) {
    if (key === "schemas") continue;
    const group = ((prop as Record<string, unknown>)?.["ui:group"] as string) || "通用";
    if (!groups.has(group)) {
      groups.set(group, []);
    }
    groups.get(group)!.push([key, prop as T]);
  }

  return groups;
}

/**
 * 获取有序的分组名列表
 * "基础参数" 排最前，"通用" 排最后，其余按字母排序
 */
export function getOrderedGroupNames(groups: Map<string, unknown[]>): string[] {
  const names = Array.from(groups.keys());
  const first: string[] = [];
  const middle: string[] = [];
  const last: string[] = [];

  for (const name of names) {
    if (name === "通用" || name === "General") {
      last.push(name);
    } else if (name === "基础参数" || name === "Basic") {
      first.push(name);
    } else {
      middle.push(name);
    }
  }

  middle.sort((a, b) => a.localeCompare(b, "zh-CN"));
  return [...first, ...middle, ...last];
}

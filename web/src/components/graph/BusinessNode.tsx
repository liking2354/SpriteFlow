import { memo, useMemo, useCallback, useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Dropdown, type DropdownOption } from "@/components/ui/Dropdown";
import { Segment } from "@/components/ui/Segment";
import type { NodeParamSchema, NodeSchema, TemplateType } from "@/api/types";

export interface BusinessNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  params: Record<string, unknown>;
  schema?: NodeSchema;
  collapsed?: boolean;
  status?: "idle" | "pending" | "queued" | "running" | "completed" | "failed";
  cacheHit?: boolean;
  /** 参数变更回调（由 PipelineCanvas 注入） */
  onParamChange?: (nodeId: string, params: Record<string, unknown>) => void;
  /** 折叠状态变更回调（由 PipelineCanvas 注入） */
  onCollapsedChange?: (nodeId: string, collapsed: boolean) => void;
}

/* ====================== 类型颜色映射 ====================== */
const TYPE_COLORS: Record<string, { accent: string; soft: string; glow: string }> = {
  CharacterMaster:  { accent: "#3b82f6", soft: "rgba(59,130,246,0.10)", glow: "rgba(59,130,246,0.30)" },
  DirectionVariant:{ accent: "#10b981", soft: "rgba(16,185,129,0.10)", glow: "rgba(16,185,129,0.30)" },
  AnimationSprite: { accent: "#f59e0b", soft: "rgba(245,158,11,0.10)", glow: "rgba(245,158,11,0.30)" },
  SkillVFX:        { accent: "#6366f1", soft: "rgba(99,102,241,0.10)", glow: "rgba(99,102,241,0.30)" },
  ImageFusion:     { accent: "#ec4899", soft: "rgba(236,72,153,0.10)", glow: "rgba(236,72,153,0.30)" },
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#f59e0b",
  queued: "#a78bfa",
  running: "#3b82f6",
  completed: "#10b981",
  failed: "#ef4444",
};

const TYPE_ICONS: Record<string, string> = {
  CharacterMaster:  "👤",
  DirectionVariant: "🧭",
  AnimationSprite:  "🏃",
  SkillVFX:         "💥",
  ImageFusion:      "🖼️",
};

const TYPE_LABELS_MAP: Record<string, string> = {
  spec: "规格书",
  character: "角色",
  direction: "方向",
  action: "动作",
  vfx: "特效",
  custom: "自定义",
};

const TYPE_I18N_KEYS: Record<string, string> = {
  CharacterMaster:  "graph.characterMaster",
  DirectionVariant: "graph.directionVariant",
  AnimationSprite:  "graph.animationSprite",
  SkillVFX:         "graph.skillVFX",
  ImageFusion:      "graph.imageFusion",
};

/* ====================== 共享组件样式 ====================== */

const widgetBase: React.CSSProperties = {
  width: "100%",
  height: 28,
  padding: "0 8px",
  fontSize: 11,
  fontFamily: "inherit",
  color: "#c8c8d4",
  background: "#0d0d1a",
  border: "1px solid #2a2a4a",
  borderRadius: 4,
  outline: "none",
  boxSizing: "border-box",
  cursor: "pointer",
};

const widgetTextarea: React.CSSProperties = {
  ...widgetBase,
  height: 52,
  padding: "6px 8px",
  resize: "none",
  cursor: "text",
  lineHeight: 1.4,
};

const sizeBtnBase = (active: boolean, accentColor: string): React.CSSProperties => ({
  flex: 1,
  height: 24,
  padding: 0,
  fontSize: 10,
  fontWeight: 600,
  fontFamily: "inherit",
  color: active ? "#fff" : "#6c7488",
  background: active ? accentColor : "#0d0d1a",
  border: `1px solid ${active ? accentColor : "#2a2a4a"}`,
  borderRadius: 3,
  cursor: "pointer",
  transition: "all 0.15s ease",
});

/* ====================== 内联 Widget 子组件 ====================== */

interface WidgetRowProps {
  label?: string;
  required?: boolean;
  children: React.ReactNode;
}
function WidgetRow({ label, required, children }: WidgetRowProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {label && (
        <span style={{ fontSize: 9.5, fontWeight: 600, color: "#6c7488", textTransform: "uppercase", letterSpacing: 0.3 }}>
          {label}{required && <span style={{ color: "#ef4444", marginLeft: 2 }}>*</span>}
        </span>
      )}
      {children}
    </div>
  );
}

function SizeButtons({
  value,
  accentColor,
  onChange,
}: {
  value: string;
  accentColor: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      {["2k", "3k", "4k"].map((s) => (
        <button
          key={s}
          type="button"
          style={sizeBtnBase(s === value, accentColor)}
          onClick={() => onChange(s)}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

/* ====================== BusinessNode ====================== */

export const BusinessNode = memo(function BusinessNode({
  id: nodeId,
  data,
  selected,
}: NodeProps) {
  const { t } = useTranslation();
  const d = data as unknown as BusinessNodeData;
  const schemasQuery = useQuery({
    queryKey: ["node-schemas", "pipeline"],
    queryFn: () => api.listNodesByCategory("pipeline"),
    staleTime: 60_000,
  });
  const schema = d.schema ?? schemasQuery.data?.find((s) => s.type === d.nodeType);
  const baseColors = TYPE_COLORS[d.nodeType] ?? TYPE_COLORS.CharacterMaster;
  const colors = schema?.color
    ? { accent: schema.color, soft: `${schema.color}1a`, glow: `${schema.color}4d` }
    : baseColors;
  const fallbackMeta = { icon: TYPE_ICONS[d.nodeType] ?? "📦", label: t(TYPE_I18N_KEYS[d.nodeType] ?? "graph.unknown", d.nodeType) as string };
  const meta = { icon: schema?.icon ?? fallbackMeta.icon, label: schema?.label ?? fallbackMeta.label };
  const inputPorts = schema?.inputs ?? (d.nodeType === "CharacterMaster" ? {} : { image: "IMAGE" });
  const outputPorts = schema?.outputs ?? (d.nodeType === "DirectionVariant" || d.nodeType === "AnimationSprite" || d.nodeType === "SkillVFX" ? { images: "IMAGE_BATCH" } : { image: "IMAGE" });
  const statusColor = d.status ? STATUS_COLORS[d.status] : undefined;
  const isRunning = d.status === "running";

  // 处理参数变更
  const updateParam = useCallback(
    (key: string, value: unknown) => {
      const newParams = { ...d.params, [key]: value };
      d.onParamChange?.(nodeId, newParams as Record<string, unknown>);
    },
    [d.params, d.onParamChange, nodeId]
  );

  // 折叠状态：从 data 读取（受控模式），不再使用本地 useState
  const collapsed = (d.ui as Record<string, unknown> | undefined)?.["collapsed"] as boolean
    ?? d.collapsed ?? false;

  const toggleCollapsed = useCallback(() => {
    const next = !collapsed;
    // 通过回调通知父组件，由父组件更新图数据
    d.onCollapsedChange?.(nodeId, next);
  }, [collapsed, d.onCollapsedChange, nodeId]);

  return (
    <div
      className="comfy-node"
      style={{
        borderColor: d.status === "failed"
          ? "#ef4444"
          : selected
            ? colors.accent
            : "#2a2a4a",
        borderWidth: d.status === "failed" ? 2 : 1,
        boxShadow: d.status === "failed"
          ? "0 0 20px rgba(239,68,68,0.30), 0 2px 12px rgba(0,0,0,0.4)"
          : selected
            ? `0 0 20px ${colors.glow}, 0 2px 12px rgba(0,0,0,0.4)`
            : isRunning
              ? `0 0 16px ${colors.glow}, 0 2px 8px rgba(0,0,0,0.3)`
              : "0 2px 8px rgba(0,0,0,0.3)",
        animation: isRunning ? "node-pulse 1.5s ease-in-out infinite" : "none",
      }}
    >
      {/* 类型色条 */}
      <div style={{ height: 2, background: colors.accent, flexShrink: 0 }} />

      {/* 头部 */}
      <div
        onClick={toggleCollapsed}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 8px",
          fontSize: 10.5,
          fontWeight: 600,
          color: "#c8c8d4",
          cursor: "pointer",
          userSelect: "none",
          borderBottom: collapsed ? "none" : "1px solid #1f1f35",
          background: d.status === "failed" ? "rgba(239,68,68,0.08)" : undefined,
        }}
      >
        {/* 状态灯 */}
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            flexShrink: 0,
            background: statusColor ?? "#454c5e",
            boxShadow: statusColor ? `0 0 5px ${statusColor}` : undefined,
            animation: isRunning ? "status-blink 0.8s ease-in-out infinite" : "none",
          }}
        />
        <span style={{ opacity: 0.7 }}>{meta.icon}</span>
        <span style={{ flex: 1 }}>{meta.label}</span>
        {d.cacheHit && (
          <span
            style={{
              fontSize: 9,
              padding: "1px 5px",
              borderRadius: 3,
              background: colors.soft,
              color: colors.accent,
            }}
          >
            {t("graph.cached", "缓存")}
          </span>
        )}
        <span style={{ fontSize: 9, color: "#454c5e", opacity: 0.6 }}>
          {collapsed ? "▶" : "▼"}
        </span>
      </div>

      {/* 输入端口 */}
      {Object.entries(inputPorts).map(([port, portType], index, arr) => (
        <Handle
          key={`in-${port}`}
          type="target"
          position={Position.Left}
          id={port}
          title={`${port}: ${portType}`}
          className="comfy-handle"
          style={{
            top: arr.length <= 1 ? "50%" : `${34 + (index * 36) / Math.max(arr.length - 1, 1)}%`,
            background: colors.accent,
            borderColor: colors.accent,
          }}
        />
      ))}

      {/* 输出端口 */}
      {Object.entries(outputPorts).map(([port, portType], index, arr) => (
        <Handle
          key={`out-${port}`}
          type="source"
          position={Position.Right}
          id={port}
          title={`${port}: ${portType}`}
          className={index === 0 ? "comfy-handle" : "comfy-handle-sub"}
          style={{
            top: arr.length <= 1 ? "50%" : `${30 + (index * 44) / Math.max(arr.length - 1, 1)}%`,
            background: colors.accent,
            borderColor: colors.accent,
          }}
        />
      ))}

      {!collapsed && (
        <div style={{ padding: "6px 8px", display: "flex", flexDirection: "column", gap: 5 }}>
          {/* ====== 参数 Widgets ====== */}
          <NodeParams schema={schema} nodeType={d.nodeType} params={d.params} updateParam={updateParam} colors={colors} />
        </div>
      )}
    </div>
  );
});

/* ====================== TemplatePickerWidget — Portal 弹出 + 类型级联选择 ====================== */

interface TemplatePickerWidgetProps {
  paramName: string;
  label: string;
  required?: boolean;
  options: DropdownOption[];
  value: string;
  accentColor: string;
  help?: string | null;
  onChange: (name: string, value: string, checked: boolean) => void;
}

function TemplatePickerWidget({
  paramName,
  label,
  required,
  options,
  value,
  accentColor,
  help,
  onChange,
}: TemplatePickerWidgetProps) {
  const [open, setOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string>("全部");
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  const selected = value.split(",").map((v) => v.trim()).filter(Boolean);

  // 分组
  const groupMap = new Map<string, DropdownOption[]>();
  for (const opt of options) {
    const g = opt.group ?? "未分类";
    if (!groupMap.has(g)) groupMap.set(g, []);
    groupMap.get(g)!.push(opt);
  }
  const typeNames = ["全部", ...Array.from(groupMap.keys())];
  const filteredOpts = typeFilter === "全部"
    ? options
    : (groupMap.get(typeFilter) ?? []);

  // 选中的模板名
  const selectedLabels = options
    .filter((o) => selected.includes(o.value))
    .map((o) => o.label);

  // 计算弹出位置
  const calcPopoverStyle = (): React.CSSProperties => {
    if (!triggerRef.current) return {};
    const rect = triggerRef.current.getBoundingClientRect();
    return {
      position: "fixed",
      zIndex: 9999,
      top: rect.bottom + 4,
      left: rect.left,
      minWidth: 220,
      maxWidth: 300,
      maxHeight: 280,
    };
  };

  // 外部点击 / 滚轮关闭
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (triggerRef.current?.contains(e.target as Node)) return;
      if (popoverRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <WidgetRow label={label} required={required}>
      {/* 触发器 */}
      <div
        ref={triggerRef}
        onClick={() => setOpen(!open)}
        style={{
          ...widgetBase,
          background: open ? "rgba(255,255,255,0.04)" : "#0d0d1a",
          borderColor: open ? accentColor : "#2a2a4a",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4,
          minHeight: 28, height: "auto", padding: "2px 6px",
        }}
      >
        <span style={{ fontSize: 10, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: selected.length > 0 ? "#c8c8d4" : "#454c5e" }}>
          {selected.length > 0 ? selectedLabels.join(", ") : "选择模板..."}
        </span>
        <svg width="10" height="10" viewBox="0 0 10 10" style={{ flexShrink: 0, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
          <path d="M3 3.5L5 5.5L7 3.5" stroke="#6c7488" strokeWidth="1.2" fill="none" strokeLinecap="round" />
        </svg>
      </div>

      {/* Popover → Portal */}
      {open && createPortal(
        <div
          ref={popoverRef}
          className="rounded-m border shadow-[0_12px_40px_rgba(0,0,0,0.5)] overflow-hidden flex flex-col"
          style={{
            ...calcPopoverStyle(),
            background: "#111127",
            borderColor: "#2a2a4a",
          }}
        >
          {/* 类型筛选标签 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 3, padding: "6px 8px", borderBottom: "1px solid #1f1f35" }}>
            {typeNames.map((tn) => (
              <button
                key={tn}
                type="button"
                style={sizeBtnBase(tn === typeFilter, accentColor)}
                onClick={() => setTypeFilter(tn)}
              >
                {tn}
              </button>
            ))}
          </div>

          {/* 选项列表 */}
          <div style={{ overflowY: "auto", flex: 1, padding: "4px 0" }}>
            {filteredOpts.length === 0 ? (
              <div style={{ fontSize: 10, color: "#454c5e", textAlign: "center", padding: "12px 0" }}>暂无可选模板</div>
            ) : (
              filteredOpts.map((opt) => {
                const active = selected.includes(opt.value);
                return (
                  <div
                    key={opt.value}
                    onClick={() => onChange(paramName, opt.value, !active)}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "4px 10px", fontSize: 10.5, cursor: "pointer",
                      color: active ? accentColor : "#9ca3af",
                      background: active ? `${accentColor}15` : undefined,
                    }}
                    onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
                    onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = ""; }}
                  >
                    <span style={{ width: 14, height: 14, borderRadius: 2, border: `1.5px solid ${active ? accentColor : "#454c5e"}`, background: active ? accentColor : "transparent", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {active && (
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 5L4 7L8 3" stroke="#fff" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      )}
                    </span>
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{opt.label}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>,
        document.body
      )}
      {help && <span style={{ fontSize: 9, color: "#454c5e", marginTop: 2 }}>{help}</span>}
    </WidgetRow>
  );
}

/* ====================== NodeParams — 内联参数区 ====================== */

interface NodeParamsProps {
  schema?: NodeSchema;
  nodeType: string;
  params: Record<string, unknown>;
  updateParam: (key: string, value: unknown) => void;
  colors: { accent: string; soft: string; glow: string };
}

function NodeParams({ schema, nodeType, params, updateParam, colors }: NodeParamsProps) {
  const { t } = useTranslation();

  const templatesQuery = useQuery({ queryKey: ["templates"], queryFn: () => api.listTemplates(), staleTime: 30_000 });
  const schemasQuery = useQuery({
    queryKey: ["node-schemas", "pipeline"],
    queryFn: () => api.listNodesByCategory("pipeline"),
    staleTime: 60_000,
    enabled: !schema,
  });
  const activeSchema = schema ?? schemasQuery.data?.find((s) => s.type === nodeType);
  const rawParamSchemas = activeSchema?.params ?? fallbackParamSchemas(nodeType);

  // 补丁：API schema 中 output_format/watermark 没有 widget/choices，需要强制修复
  const paramSchemas = useMemo(() => rawParamSchemas.map((p) => {
    if (p.name === "output_format" && (!p.widget || p.widget === "text")) {
      return { ...p, widget: "select" as const, choices: ["png", "webp", "jpeg"] };
    }
    if (p.name === "watermark" && (!p.widget || p.widget === "text")) {
      return { ...p, widget: "select" as const, choices: ["true", "false"] };
    }
    if (p.name === "size" && !p.widget) {
      return { ...p, widget: "size" as const };
    }
    if (p.name === "template_ids") {
      return { ...p, widget: "template_picker" as const, options_source: "templates" as const };
    }
    return p;
  }), [rawParamSchemas]);

  const [defaultsOpen, setDefaultsOpen] = useState(false);

  const optionsFor = (param: NodeParamSchema): DropdownOption[] => {
    if (param.choices?.length) return param.choices.map((v) => ({ value: v, label: v }));
    const all = templatesQuery.data?.templates ?? [];
    if (param.options_source === "templates") return all.map((t) => ({ value: t.id, label: t.name, group: TYPE_LABELS_MAP[t.type] ?? t.type }));
    if (param.options_source === "specs") return all.filter(t => t.type === "spec").map((t) => ({ value: t.id, label: t.name }));
    if (param.options_source === "characters") return all.filter(t => t.type === "character").map((t) => ({ value: t.id, label: t.name }));
    if (param.options_source === "actions") return all.filter(t => t.type === "action").map((t) => ({ value: t.id, label: t.name }));
    if (param.options_source === "vfx") return all.filter(t => t.type === "vfx").map((t) => ({ value: t.id, label: t.name }));
    return [];
  };

  const setCommaValue = (name: string, value: string, checked: boolean) => {
    const current = String(params[name] ?? "").split(",").map((v) => v.trim()).filter(Boolean);
    const next = checked ? Array.from(new Set([...current, value])) : current.filter((v) => v !== value);
    updateParam(name, next.join(","));
  };

  const renderParam = (param: NodeParamSchema) => {
    const value = params[param.name] ?? param.default ?? "";
    const missing = param.required && (value === "" || value === null || value === undefined);
    const style = missing ? { ...widgetBase, borderColor: "#ef4444" } : widgetBase;
    const label = param.label ?? param.name;
    const options = optionsFor(param);

    if (param.widget === "size") {
      return (
        <WidgetRow key={param.name} label={label} required={param.required}>
          <SizeButtons value={String(value || "2k")} accentColor={colors.accent} onChange={(v) => updateParam(param.name, v)} />
        </WidgetRow>
      );
    }

    if (param.widget === "textarea") {
      return (
        <WidgetRow key={param.name} label={label} required={param.required}>
          <textarea
            style={missing ? { ...widgetTextarea, borderColor: "#ef4444" } : widgetTextarea}
            placeholder={param.placeholder ?? ""}
            value={String(value ?? "")}
            onChange={(e) => updateParam(param.name, e.target.value)}
          />
        </WidgetRow>
      );
    }

    if (param.widget === "template_picker") {
      return (
        <TemplatePickerWidget
          key={param.name}
          paramName={param.name}
          label={label}
          required={param.required}
          options={options}
          value={String(value ?? "")}
          accentColor={colors.accent}
          help={param.help}
          onChange={setCommaValue}
        />
      );
    }

    if (param.widget === "multi_select") {
      return (
        <TemplatePickerWidget
          key={param.name}
          paramName={param.name}
          label={label}
          required={param.required}
          options={options}
          value={String(value ?? "")}
          accentColor={colors.accent}
          help={param.help}
          onChange={setCommaValue}
        />
      );
    }

    if (param.widget === "select" || options.length > 0) {
      // 使用 Dropdown 组件，带类型分组
      const placeholder = param.required
        ? (t("graph.pleaseSelect", "— 请选择 —") as string)
        : (t("graph.optional", "— 可选 —") as string);

      return (
        <WidgetRow key={param.name} label={label} required={param.required}>
          <Dropdown
            options={options}
            value={String(value ?? "")}
            placeholder={placeholder}
            width={undefined}
            onChange={(v) => updateParam(param.name, v || undefined)}
          />
        </WidgetRow>
      );
    }

    if (param.widget === "number" || param.type === "int" || param.type === "float" || param.type === "seed") {
      return (
        <WidgetRow key={param.name} label={label} required={param.required}>
          <input
            type="number"
            style={style}
            min={param.min ?? undefined}
            max={param.max ?? undefined}
            value={value === null || value === undefined ? "" : Number(value)}
            onChange={(e) => updateParam(param.name, e.target.value === "" ? undefined : Number(e.target.value))}
          />
        </WidgetRow>
      );
    }

    return (
      <WidgetRow key={param.name} label={label} required={param.required}>
        <input
          type="text"
          style={style}
          placeholder={param.placeholder ?? ""}
          value={String(value ?? "")}
          onChange={(e) => updateParam(param.name, e.target.value)}
        />
      </WidgetRow>
    );
  };

  function fallbackParamSchemas(nodeType: string): NodeParamSchema[] {
    const size: NodeParamSchema = { name: "size", type: "str", label: t("graph.size", "尺寸"), widget: "size", default: "2k", required: false, min: null, max: null, choices: null };
    const seed: NodeParamSchema = { name: "seed", type: "seed", label: t("graph.seed", "随机种子"), widget: "number", default: null, required: false, min: null, max: null, choices: null };
    const outputFormat: NodeParamSchema = { name: "output_format", type: "str", label: t("graph.outputFormat", "输出格式"), widget: "select", default: "png", required: false, min: null, max: null, choices: ["png", "webp", "jpeg"] };
    const watermark: NodeParamSchema = { name: "watermark", type: "str", label: t("graph.watermark", "水印"), widget: "select", default: "false", required: false, min: null, max: null, choices: ["true", "false"] };
    const commonCompact = [seed, outputFormat, watermark];
    const commonFull = [size];
    // CharacterMaster 独有的对齐参数
    const alignCompact: NodeParamSchema[] = [
      { name: "canvas_width", type: "int", label: t("graph.canvasWidth", "画布宽度"), widget: "number", default: 512, required: false, min: 64, max: 4096, choices: null },
      { name: "canvas_height", type: "int", label: t("graph.canvasHeight", "画布高度"), widget: "number", default: 512, required: false, min: 64, max: 4096, choices: null },
      { name: "target_width", type: "int", label: t("graph.targetWidth", "角色宽度"), widget: "number", default: 448, required: false, min: 4, max: 4096, choices: null },
      { name: "target_height", type: "int", label: t("graph.targetHeight", "角色高度"), widget: "number", default: 480, required: false, min: 4, max: 4096, choices: null },
      { name: "detect_threshold", type: "int", label: t("graph.detectThreshold", "检测阈值"), widget: "number", default: 32, required: false, min: 0, max: 255, choices: null },
    ];
    const map: Record<string, NodeParamSchema[]> = {
      CharacterMaster: [
        { name: "template_ids", type: "str", label: t("graph.templateIds", "模板"), widget: "template_picker", default: "", required: false, min: null, max: null, choices: null, options_source: "templates", help: "先选类型再选模板" },
        { name: "slot_values", type: "json", label: t("graph.slotValues", "槽位值"), widget: "text", default: "{}", required: false, min: null, max: null, choices: null },
        { name: "style_prompt", type: "str", label: t("graph.stylePrompt", "风格提示词"), widget: "textarea", default: "", required: false, min: null, max: null, choices: null },
        ...commonFull,
        ...alignCompact,
        ...commonCompact,
      ],
      DirectionVariant: [
        { name: "template_ids", type: "str", label: t("graph.templateIds", "方向模板"), widget: "template_picker", default: "", required: false, min: null, max: null, choices: null, options_source: "templates" },
        { name: "slot_values", type: "json", label: t("graph.slotValues", "槽位值"), widget: "text", default: "{}", required: false, min: null, max: null, choices: null },
        ...commonFull,
        ...commonCompact,
      ],
      AnimationSprite: [
        { name: "template_ids", type: "str", label: t("graph.templateIds", "动作模板"), widget: "template_picker", default: "", required: false, min: null, max: null, choices: null, options_source: "templates" },
        { name: "slot_values", type: "json", label: t("graph.slotValues", "槽位值"), widget: "text", default: "{}", required: false, min: null, max: null, choices: null },
        { name: "max_images", type: "int", label: t("graph.maxImages", "最大帧数"), widget: "number", default: 1, required: false, min: 1, max: 64, choices: null },
        ...commonFull,
        ...commonCompact,
      ],
      SkillVFX: [
        { name: "template_ids", type: "str", label: t("graph.templateIds", "特效模板"), widget: "template_picker", default: "", required: false, min: null, max: null, choices: null, options_source: "templates" },
        { name: "slot_values", type: "json", label: t("graph.slotValues", "槽位值"), widget: "text", default: "{}", required: false, min: null, max: null, choices: null },
        ...commonFull,
        ...commonCompact,
      ],
      ImageFusion: [
        { name: "template_ids", type: "str", label: t("graph.templateIds", "融合模板"), widget: "template_picker", default: "", required: false, min: null, max: null, choices: null, options_source: "templates" },
        { name: "slot_values", type: "json", label: t("graph.slotValues", "槽位值"), widget: "text", default: "{}", required: false, min: null, max: null, choices: null },
        ...commonFull,
        ...commonCompact,
      ],
    };
    return map[nodeType] ?? [];
  }

  // 紧凑参数集（2 列网格，默认隐藏）：number/select 类型的短参数
  // size（尺寸选择器）单独全宽一行，不入网格
  const compactParamNames = new Set(["seed", "output_format", "watermark", "canvas_width", "canvas_height", "target_width", "target_height", "detect_threshold", "max_images"]);
  const mainParams = paramSchemas.filter((p) => !compactParamNames.has(p.name));
  const compactParams = paramSchemas.filter((p) => compactParamNames.has(p.name));

  return (
    <>
      {mainParams.map(renderParam)}
      {compactParams.length > 0 && (
        <>
          {/* 展开/收起紧凑参数 */}
          <div
            onClick={() => setDefaultsOpen(v => !v)}
            style={{
              fontSize: 9.5, fontWeight: 600, color: "#6c7488", cursor: "pointer",
              textTransform: "uppercase", letterSpacing: 0.3, userSelect: "none",
              display: "flex", alignItems: "center", gap: 4, paddingTop: 2,
            }}
          >
            <span style={{ fontSize: 9, color: "#454c5e", transition: "transform 0.15s", transform: defaultsOpen ? "rotate(90deg)" : "none" }}>
              ▶
            </span>
            {t("graph.defaultParams", "默认参数")}
          </div>
          {defaultsOpen && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 6px" }}>
              {compactParams.map(renderParam)}
            </div>
          )}
        </>
      )}
    </>
  );
}

export default BusinessNode;

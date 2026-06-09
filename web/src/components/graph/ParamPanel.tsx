import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { TextInput, TextArea, Switch } from "@/components/ui/Field";
import { Segment } from "@/components/ui/Segment";
import { Dropdown } from "@/components/ui/Dropdown";
import type { PipelineNodeParams, PromptTemplate, TemplateType } from "@/api/types";

/* ──────────── 常量 ──────────── */

const NODE_TEMPLATE_TYPES: Record<string, TemplateType[]> = {
  CharacterMaster: ["spec", "character"],
  DirectionVariant: ["direction"],
  AnimationSprite: ["action"],
  SkillVFX: ["vfx"],
  ImageFusion: ["custom"],
};

const TYPE_LABELS: Record<string, string> = {
  spec: "规格书", character: "角色", direction: "方向", action: "动作", vfx: "特效", custom: "自定义",
};

interface ParamDef {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "textarea" | "toggle";
  default?: string | number | boolean;
  placeholder?: string;
  options?: string[];
  min?: number;
  max?: number;
  dependsOn?: string;
}

/* ──────────── 系统参数定义 ──────────── */

const SYSTEM_PARAMS: Record<string, ParamDef[]> = {
  CharacterMaster: [
    { name: "style_prompt", label: "风格提示词", type: "textarea", default: "", placeholder: "pixel art, dark armor, red cape..." },
    { name: "size", label: "尺寸", type: "select", default: "2k", options: ["2k", "3k", "4k"] },
    { name: "enable_remove_bg", label: "去背景", type: "toggle", default: false },
    { name: "enable_sprite_align", label: "精灵对齐", type: "toggle", default: true },
    { name: "canvas_width", label: "画布宽度", type: "number", default: 512, min: 64, max: 4096, dependsOn: "enable_sprite_align" },
    { name: "canvas_height", label: "画布高度", type: "number", default: 512, min: 64, max: 4096, dependsOn: "enable_sprite_align" },
    { name: "target_width", label: "角色宽度", type: "number", default: 448, min: 4, max: 4096, dependsOn: "enable_sprite_align" },
    { name: "target_height", label: "角色高度", type: "number", default: 480, min: 4, max: 4096, dependsOn: "enable_sprite_align" },
    { name: "detect_threshold", label: "检测阈值", type: "number", default: 32, min: 0, max: 255, dependsOn: "enable_sprite_align" },
    { name: "padding", label: "边距", type: "number", default: 8, min: 0, max: 64, dependsOn: "enable_sprite_align" },
  ],
};

const DEFAULT_PARAMS: Record<string, ParamDef[]> = {
  CharacterMaster: [
    { name: "seed", label: "随机种子", type: "number", default: 0 },
    { name: "watermark", label: "水印", type: "select", default: "false", options: ["true", "false"] },
    { name: "output_format", label: "输出格式", type: "select", default: "png", options: ["png", "webp", "jpeg"] },
  ],
  DirectionVariant: [
    { name: "size", label: "尺寸", type: "select", default: "2k", options: ["2k", "3k", "4k"] },
    { name: "output_format", label: "输出格式", type: "select", default: "png", options: ["png", "webp", "jpeg"] },
    { name: "seed", label: "随机种子", type: "number", default: 0 },
    { name: "watermark", label: "水印", type: "select", default: "false", options: ["true", "false"] },
  ],
  AnimationSprite: [
    { name: "max_images", label: "最大帧数", type: "number", default: 1, min: 1, max: 64 },
    { name: "size", label: "尺寸", type: "select", default: "2k", options: ["2k", "3k", "4k"] },
    { name: "output_format", label: "输出格式", type: "select", default: "png", options: ["png", "webp", "jpeg"] },
    { name: "seed", label: "随机种子", type: "number", default: 0 },
    { name: "watermark", label: "水印", type: "select", default: "false", options: ["true", "false"] },
  ],
  SkillVFX: [
    { name: "size", label: "尺寸", type: "select", default: "2k", options: ["2k", "3k", "4k"] },
    { name: "output_format", label: "输出格式", type: "select", default: "png", options: ["png", "webp", "jpeg"] },
    { name: "seed", label: "随机种子", type: "number", default: 0 },
    { name: "watermark", label: "水印", type: "select", default: "false", options: ["true", "false"] },
  ],
};

/* ──────────── ParamPanel 主组件 ──────────── */

interface ParamPanelProps {
  nodeType: string | null;
  params: PipelineNodeParams;
  onChange: (params: PipelineNodeParams) => void;
}

export function ParamPanel({ nodeType, params, onChange }: ParamPanelProps) {
  const { t } = useTranslation();

  const templatesQuery = useQuery({
    queryKey: ["templates"],
    queryFn: () => api.listTemplates(),
    staleTime: 30_000,
  });

  if (!nodeType) {
    return (
      <div className="flex items-center justify-center h-full text-[11px]" style={{ color: "var(--txt-3)" }}>
        {t("graph.selectNode", "点击节点查看参数")}
      </div>
    );
  }

  const update = (key: string, value: unknown) => {
    onChange({ ...params, [key]: value });
  };

  const templates = templatesQuery.data?.templates ?? [];
  const isTemplatesLoading = templatesQuery.isLoading;
  const allowedTypes = NODE_TEMPLATE_TYPES[nodeType] ?? [];
  const systemFields = SYSTEM_PARAMS[nodeType];
  const defaultFields = DEFAULT_PARAMS[nodeType];

  const selectedIds = useMemo((): string[] => {
    const raw = params.template_ids ?? "";
    if (typeof raw === "string") return raw.split(",").map((s) => s.trim()).filter(Boolean);
    if (Array.isArray(raw)) return (raw as string[]).filter(Boolean);
    return [];
  }, [params.template_ids]);

  const selectedTemplates = useMemo(
    () => templates.filter((t) => selectedIds.includes(t.id)),
    [templates, selectedIds],
  );

  const toggleTemplateId = (id: string) => {
    const next = selectedIds.includes(id)
      ? selectedIds.filter((v) => v !== id)
      : [...selectedIds, id];
    update("template_ids", next.join(","));
  };

  const updateSlotValue = (slotName: string, value: string) => {
    update("slot_values", { ...(params.slot_values ?? {}), [slotName]: value });
  };

  // 分离系统参数中的对齐子参数
  const alignmentFields = systemFields?.filter((f) => f.dependsOn === "enable_sprite_align") ?? [];
  const mainSystemFields = systemFields?.filter((f) => f.dependsOn !== "enable_sprite_align") ?? [];
  const spriteAlignEnabled = (() => {
    const v = params.enable_sprite_align;
    if (typeof v === "boolean") return v;
    return String(v ?? true) === "true";
  })();

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* 标题栏 */}
      <div
        className="px-3 py-2.5 text-[11px] font-semibold border-b sticky top-0 z-10 flex items-center gap-1.5"
        style={{ color: "var(--txt-2)", borderColor: "var(--line)", background: "var(--bg-1)" }}
      >
        <span style={{ color: "var(--acc)", fontSize: 13 }}>⚙</span>
        {t("graph.params", "节点参数")}
        <span className="text-[10px] font-normal" style={{ color: "var(--txt-3)" }}>
          · {nodeType}
        </span>
      </div>

      <div className="flex flex-col">
        {/* ── 1. 模版ID ── */}
        {allowedTypes.length > 0 && (
          <CollapsibleSection title={t("graph.templateIds", "模版ID")} defaultOpen>
            <TemplateTypeSelector
              key={nodeType}
              nodeType={nodeType}
              templates={templates}
              selectedIds={selectedIds}
              onToggle={toggleTemplateId}
              isLoading={isTemplatesLoading}
            />
          </CollapsibleSection>
        )}

        {/* ── 2. 系统参数 ── */}
        {systemFields && systemFields.length > 0 && (
          <CollapsibleSection title={t("graph.systemParams", "系统参数")} defaultOpen>
            <div className="flex flex-col gap-2.5">
              {mainSystemFields.map((f) => (
                <ParamRow key={f.name} field={f} params={params} update={update} />
              ))}

              {/* 对齐参数子卡片 */}
              {spriteAlignEnabled && alignmentFields.length > 0 && (
                <div
                  className="mt-1 rounded-md border p-2.5"
                  style={{ borderColor: "var(--line-soft)", background: "var(--bg-0)" }}
                >
                  <div className="text-[10px] font-semibold mb-2 uppercase tracking-wider" style={{ color: "var(--txt-3)" }}>
                    {t("graph.alignParams", "对齐参数")}
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                    {alignmentFields.map((f) => (
                      <ParamRowCompact key={f.name} field={f} params={params} update={update} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* ── 3. 模版参数（动态 Slots）── */}
        {selectedTemplates.length > 0 && (
          <CollapsibleSection title={t("graph.templateParams", "模版参数")} defaultOpen>
            <SlotFields
              templates={selectedTemplates}
              slotValues={params.slot_values ?? {}}
              onUpdate={updateSlotValue}
            />
          </CollapsibleSection>
        )}

        {/* ── 4. 默认参数 ── */}
        {defaultFields && defaultFields.length > 0 && (
          <CollapsibleSection title={t("graph.defaultParams", "默认参数")} defaultOpen={false}>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2">
              {defaultFields.map((f) => (
                <ParamRowCompact key={f.name} field={f} params={params} update={update} />
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>
    </div>
  );
}

/* ──────────── 子组件 ──────────── */

/** 折叠面板 */
function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b" style={{ borderColor: "var(--line-soft)" }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-3 py-2 hover:brightness-110 transition-all"
        style={{ background: "var(--bg-0)" }}
      >
        <span
          className="text-[9px] transition-transform duration-150"
          style={{ color: "var(--txt-3)", transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
        >
          ▶
        </span>
        <span
          className="text-[10px] font-semibold uppercase tracking-wider"
          style={{ color: "var(--txt-2)" }}
        >
          {title}
        </span>
      </button>
      {open && <div className="px-3 pb-3 pt-1">{children}</div>}
    </div>
  );
}

/** 参数行 — 全宽控件（textarea / toggle） */
function ParamRow({
  field,
  params,
  update,
}: {
  field: ParamDef;
  params: PipelineNodeParams;
  update: (k: string, v: unknown) => void;
}) {
  const v = params[field.name];
  const strVal = v !== undefined && v !== null ? String(v) : "";

  if (field.type === "toggle") {
    const checked = typeof v === "boolean" ? v : String(v ?? field.default ?? false) === "true";
    return (
      <div className="flex items-center justify-between py-0.5">
        <span className="text-[10.5px] font-medium" style={{ color: "var(--txt-2)" }}>
          {field.label}
        </span>
        <Switch checked={checked} onChange={(val) => update(field.name, val)} />
      </div>
    );
  }

  if (field.type === "textarea") {
    return (
      <div className="flex flex-col gap-1">
        <span className="text-[10.5px] font-medium" style={{ color: "var(--txt-2)" }}>
          {field.label}
        </span>
        <TextArea
          className="text-[11px] h-16"
          placeholder={field.placeholder ?? ""}
          value={strVal}
          onChange={(e) => update(field.name, e.target.value)}
        />
      </div>
    );
  }

  // select / number / text — 标签+控件同行
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 text-[10.5px] font-medium" style={{ color: "var(--txt-2)" }}>
        {field.label}
      </span>
      <div className="flex-1">
        <ParamControl field={field} params={params} update={update} />
      </div>
    </div>
  );
}

/** 紧凑参数行 — 用于 grid 中的小控件 */
function ParamRowCompact({
  field,
  params,
  update,
}: {
  field: ParamDef;
  params: PipelineNodeParams;
  update: (k: string, v: unknown) => void;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9.5px] font-medium" style={{ color: "var(--txt-3)" }}>
        {field.label}
      </span>
      <ParamControl field={field} params={params} update={update} compact />
    </div>
  );
}

/** 参数控件 — 根据类型渲染 */
function ParamControl({
  field,
  params,
  update,
  compact = false,
}: {
  field: ParamDef;
  params: PipelineNodeParams;
  update: (k: string, v: unknown) => void;
  compact?: boolean;
}) {
  const v = params[field.name];
  const strVal = v !== undefined && v !== null ? String(v) : "";
  const h = compact ? "h-7" : "h-8";

  if (field.type === "select" && field.options) {
    return (
      <Dropdown
        className={h}
        options={field.options.map((o) => ({ value: o, label: o }))}
        value={strVal || String(field.default ?? "")}
        onChange={(val) => update(field.name, val)}
      />
    );
  }

  if (field.type === "number") {
    return (
      <TextInput
        className={`${h} text-[11px]`}
        type="number"
        min={field.min}
        max={field.max}
        value={strVal || String(field.default ?? "")}
        onChange={(e) => update(field.name, e.target.value ? Number(e.target.value) : "")}
      />
    );
  }

  return (
    <TextInput
      className={`${h} text-[11px]`}
      placeholder={field.placeholder ?? ""}
      value={strVal || String(field.default ?? "")}
      onChange={(e) => update(field.name, e.target.value)}
    />
  );
}

/* ──────────── 模板选择器 ──────────── */

function TemplateTypeSelector({
  nodeType,
  templates,
  selectedIds,
  onToggle,
  isLoading,
}: {
  nodeType: string;
  templates: PromptTemplate[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  isLoading?: boolean;
}) {
  const allowedTypes = NODE_TEMPLATE_TYPES[nodeType] ?? [];
  const [activeType, setActiveType] = useState<TemplateType>(allowedTypes[0]);

  const typeItems = allowedTypes.map((t) => ({
    value: t,
    label: TYPE_LABELS[t] ?? t,
  }));

  const filtered = templates.filter((t) => t.type === activeType);
  const selectedOfType = filtered.filter((t) => selectedIds.includes(t.id));

  if (isLoading) {
    return (
      <p className="text-[10px] animate-pulse" style={{ color: "var(--txt-3)" }}>加载模板中…</p>
    );
  }

  return (
    <div className="space-y-2">
      {typeItems.length > 1 && (
        <Segment items={typeItems} value={activeType} onChange={setActiveType} />
      )}
      {selectedOfType.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selectedOfType.map((t) => (
            <span
              key={t.id}
              onClick={() => onToggle(t.id)}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] cursor-pointer transition-colors"
              style={{ background: "var(--acc)", color: "#fff" }}
            >
              {t.name}<span className="opacity-60 ml-0.5">×</span>
            </span>
          ))}
        </div>
      )}
      {filtered.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 max-h-[120px] overflow-y-auto">
          {filtered.filter((t) => !selectedIds.includes(t.id)).map((t) => (
            <span
              key={t.id}
              onClick={() => onToggle(t.id)}
              className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] cursor-pointer transition-colors border"
              style={{ color: "var(--txt-2)", borderColor: "var(--line)", background: "var(--bg-0)" }}
              onMouseEnter={(e) => { e.currentTarget.style.color = "var(--acc)"; e.currentTarget.style.borderColor = "var(--acc)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = "var(--txt-2)"; e.currentTarget.style.borderColor = "var(--line)"; }}
            >
              {t.name}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-[10px]" style={{ color: "var(--txt-3)" }}>暂无该类型模板</p>
      )}
    </div>
  );
}

/* ──────────── Slot 编辑区 ──────────── */

function SlotFields({
  templates,
  slotValues,
  onUpdate,
}: {
  templates: PromptTemplate[];
  slotValues: Record<string, string>;
  onUpdate: (name: string, value: string) => void;
}) {
  const allSlots = templates.flatMap((tpl) =>
    (tpl.slots ?? []).map((slot) => ({ ...slot, _tplName: tpl.name }))
  );
  if (allSlots.length === 0) return null;

  return (
    <div className="space-y-2">
      {allSlots.map((slot) => {
        const currentVal = slotValues[slot.name] ?? slot.default ?? "";
        return (
          <div key={slot.name} className="flex items-center gap-2">
            <span
              className="w-20 shrink-0 text-[10px] truncate text-right"
              style={{ color: "var(--txt-3)" }}
              title={`${slot._tplName} › ${slot.label || slot.name}`}
            >
              {slot.label || slot.name}
            </span>
            {slot.type === "dropdown" && (slot.options ?? []).length > 0 ? (
              <Dropdown
                className="flex-1 h-7"
                options={slot.options!.map((o) => ({ value: o, label: o }))}
                value={currentVal}
                placeholder="—"
                onChange={(v) => onUpdate(slot.name, v)}
              />
            ) : (
              <TextInput
                className="flex-1 h-7 text-[11px]"
                placeholder={slot.placeholder ?? slot.default ?? ""}
                value={currentVal}
                onChange={(e) => onUpdate(slot.name, e.target.value)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

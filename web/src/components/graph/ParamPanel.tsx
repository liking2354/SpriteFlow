import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Field, TextInput, TextArea } from "@/components/ui/Field";
import { Segment } from "@/components/ui/Segment";
import { Dropdown, type DropdownOption } from "@/components/ui/Dropdown";
import type { PipelineNodeParams, PromptTemplate, TemplateType } from "@/api/types";

// 每个节点类型对应的可选模板类型
const NODE_TEMPLATE_TYPES: Record<string, TemplateType[]> = {
  CharacterMaster: ["spec", "character"],
  DirectionVariant: ["direction"],
  AnimationSprite: ["action"],
  SkillVFX: ["vfx"],
  ImageFusion: ["custom"],
};

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
      <div className="flex items-center justify-center h-full text-[12px]" style={{ color: "var(--txt-3)" }}>
        {t("graph.selectNode", "点击画布上的节点查看参数")}
      </div>
    );
  }

  const update = (key: string, value: unknown) => {
    onChange({ ...params, [key]: value });
  };

  const templates = templatesQuery.data?.templates ?? [];
  const allowedTypes = NODE_TEMPLATE_TYPES[nodeType] ?? [];
  const defaultFields = DEFAULT_PARAMS[nodeType];

  // 解析已选模板 ID
  const parseTemplateIds = (): string[] => {
    const raw = params.template_ids ?? "";
    if (typeof raw === "string") return raw.split(",").map((s) => s.trim()).filter(Boolean);
    if (Array.isArray(raw)) return raw as string[];
    return [];
  };
  const selectedIds = parseTemplateIds();
  const selectedTemplates = templates.filter((t) => selectedIds.includes(t.id));

  const toggleTemplateId = (id: string) => {
    const next = selectedIds.includes(id)
      ? selectedIds.filter((v) => v !== id)
      : [...selectedIds, id];
    update("template_ids", next.join(","));
  };

  const updateSlotValue = (slotName: string, value: string) => {
    update("slot_values", { ...(params.slot_values ?? {}), [slotName]: value });
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* 标题栏 */}
      <div
        className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider border-b sticky top-0 z-10"
        style={{ color: "var(--txt-2)", borderColor: "var(--line-soft)", background: "var(--bg-1)" }}
      >
        {t("graph.params", "节点参数")} · {nodeType}
      </div>

      <div className="px-3 py-3 flex flex-col gap-4">
        {/* ========== 模板参数 ========== */}
        {allowedTypes.length > 0 && (
          <>
            <SectionTitle text={t("graph.templateParams", "模板参数")} />
            <TemplateTypeSelector
              key={nodeType}
              nodeType={nodeType}
              templates={templates}
              selectedIds={selectedIds}
              onToggle={toggleTemplateId}
            />
            {selectedTemplates.length > 0 && (
              <SlotFields
                templates={selectedTemplates}
                slotValues={params.slot_values ?? {}}
                onUpdate={updateSlotValue}
              />
            )}
          </>
        )}

        {/* ========== 默认参数（直接展示，不用折叠） ========== */}
        {defaultFields && defaultFields.length > 0 && (
          <>
            <SectionTitle text={t("graph.defaultParams", "默认参数")} />
            <InlineDefaultParams
              fields={defaultFields}
              params={params}
              update={update}
            />
          </>
        )}

        {/* 未配置任何参数时提示 */}
        {allowedTypes.length === 0 && (!defaultFields || defaultFields.length === 0) && (
          <p className="text-[10px]" style={{ color: "var(--txt-3)" }}>
            {t("graph.noParams", "该节点无参数配置")}
          </p>
        )}
      </div>
    </div>
  );
}

/* ──────────── 子组件 ──────────── */

function SectionTitle({ text }: { text: string }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--txt-3)" }}>
      {text}
    </div>
  );
}

/** 模板类型选择器：先选类型再选模板 */
function TemplateTypeSelector({
  nodeType,
  templates,
  selectedIds,
  onToggle,
}: {
  nodeType: string;
  templates: PromptTemplate[];
  selectedIds: string[];
  onToggle: (id: string) => void;
}) {
  const allowedTypes = NODE_TEMPLATE_TYPES[nodeType] ?? [];
  const [activeType, setActiveType] = useState<TemplateType>(allowedTypes[0]);

  const typeItems = allowedTypes.map((t) => ({
    value: t,
    label: TYPE_LABELS[t] ?? t,
  }));

  const filtered = templates.filter((t) => t.type === activeType);
  const selectedOfType = filtered.filter((t) => selectedIds.includes(t.id));

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
              {t.name}<span className="opacity-70">×</span>
            </span>
          ))}
        </div>
      )}
      {filtered.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 max-h-[120px] overflow-y-auto p-1">
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

/** Slot 编辑区 */
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
    <>
      <SectionTitle text="Slot 值" />
      <div className="space-y-1.5">
        {allSlots.map((slot) => {
          const currentVal = slotValues[slot.name] ?? slot.default ?? "";
          return (
            <div key={slot.name} className="flex items-center gap-2">
              <span
                className="w-24 shrink-0 text-[10px] truncate text-right"
                style={{ color: "var(--txt-3)" }}
                title={`${slot._tplName} › ${slot.label || slot.name}`}
              >
                {slot.label || slot.name}
              </span>
              {slot.type === "dropdown" && (slot.options ?? []).length > 0 ? (
                <Dropdown
                  className="flex-1"
                  options={slot.options!.map((o) => ({ value: o, label: o }))}
                  value={currentVal}
                  placeholder="—"
                  onChange={(v) => onUpdate(slot.name, v)}
                />
              ) : (
                <TextInput
                  className="flex-1 h-8 text-[11px]"
                  placeholder={slot.placeholder ?? slot.default ?? ""}
                  value={currentVal}
                  onChange={(e) => onUpdate(slot.name, e.target.value)}
                />
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

/** 默认参数 — 直接内联展示，紧凑两列 */
function InlineDefaultParams({
  fields,
  params,
  update,
}: {
  fields: DefaultParamDef[];
  params: PipelineNodeParams;
  update: (k: string, v: unknown) => void;
}) {
  const textareaFields = fields.filter((f) => f.type === "textarea");
  const inlineFields = fields.filter((f) => f.type !== "textarea");

  return (
    <div className="space-y-3">
      {inlineFields.length > 0 && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-2">
          {inlineFields.map((f) => {
            const v = params[f.name];
            const strVal = v !== undefined && v !== null ? String(v) : "";
            return (
              <Field key={f.name} label={f.label} className="mb-0">
                {f.type === "select" && f.options ? (
                  <Dropdown
                    options={f.options.map((o) => ({ value: o, label: o }))}
                    value={strVal || String(f.default ?? "")}
                    onChange={(val) => update(f.name, val)}
                  />
                ) : f.type === "number" ? (
                  <TextInput
                    className="h-8 text-[11px]"
                    type="number"
                    min={f.min}
                    max={f.max}
                    value={strVal || String(f.default ?? "")}
                    onChange={(e) => update(f.name, e.target.value ? Number(e.target.value) : "")}
                  />
                ) : (
                  <TextInput
                    className="h-8 text-[11px]"
                    placeholder={f.placeholder ?? ""}
                    value={strVal || String(f.default ?? "")}
                    onChange={(e) => update(f.name, e.target.value)}
                  />
                )}
              </Field>
            );
          })}
        </div>
      )}
      {textareaFields.map((f) => {
        const v = params[f.name];
        const strVal = v !== undefined && v !== null ? String(v) : "";
        return (
          <Field key={f.name} label={f.label} className="mb-0">
            <TextArea
              className="text-[11px] h-16"
              placeholder={f.placeholder ?? ""}
              value={strVal}
              onChange={(e) => update(f.name, e.target.value)}
            />
          </Field>
        );
      })}
    </div>
  );
}

/* ──────────── 常量 ──────────── */

const TYPE_LABELS: Record<string, string> = {
  spec: "规格书", character: "角色", direction: "方向", action: "动作", vfx: "特效", custom: "自定义",
};

interface DefaultParamDef {
  name: string;
  label: string;
  type: "text" | "number" | "select" | "textarea";
  default?: string | number;
  placeholder?: string;
  options?: string[];
  min?: number;
  max?: number;
}

const DEFAULT_PARAMS: Record<string, DefaultParamDef[]> = {
  CharacterMaster: [
    { name: "size", label: "尺寸", type: "select", default: "2k", options: ["2k", "3k", "4k"] },
    { name: "canvas_width", label: "画布宽度", type: "number", default: 512, min: 64, max: 4096 },
    { name: "canvas_height", label: "画布高度", type: "number", default: 512, min: 64, max: 4096 },
    { name: "target_width", label: "角色宽度", type: "number", default: 448, min: 4, max: 4096 },
    { name: "target_height", label: "角色高度", type: "number", default: 480, min: 4, max: 4096 },
    { name: "detect_threshold", label: "检测阈值", type: "number", default: 32, min: 0, max: 255 },
    { name: "output_format", label: "输出格式", type: "select", default: "png", options: ["png", "webp", "jpeg"] },
    { name: "seed", label: "随机种子", type: "number", default: 0 },
    { name: "watermark", label: "水印", type: "select", default: "false", options: ["true", "false"] },
    { name: "style_prompt", label: "风格提示词", type: "textarea", default: "", placeholder: "pixel art, dark armor, red cape..." },
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

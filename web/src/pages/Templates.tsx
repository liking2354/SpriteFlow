import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { PromptTemplate, TemplateType, PromptSlot, SlotType } from "@/api/types";

const TYPE_OPTIONS: { value: TemplateType | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "spec", label: "规格书" },
  { value: "character", label: "角色" },
  { value: "direction", label: "方向" },
  { value: "action", label: "动作" },
  { value: "vfx", label: "特效" },
  { value: "custom", label: "自定义" },
];

const PAGE_SIZES = [10, 20, 50];

const EMPTY_TEMPLATE: PromptTemplate = {
  id: "",
  name: "",
  type: "custom" as TemplateType,
  text: "",
  slots: [],
  description: "",
  tags: [],
  created_at: "",
  updated_at: "",
};

function slotTypeLabel(st: string, t: ReturnType<typeof useTranslation>["t"]): string {
  return st === "dropdown" ? t("templates.slotType.dropdown") : t("templates.slotType.input");
}

export function TemplatesPage() {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<TemplateType | "all">("all");
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // 编辑态
  const [editing, setEditing] = useState<PromptTemplate | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  // 批量删除选中
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  // 单条预览
  const [previewTpl, setPreviewTpl] = useState<PromptTemplate | null>(null);
  const [previewSlotValues, setPreviewSlotValues] = useState<Record<string, string>>({});
  const [previewResult, setPreviewResult] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const offset = (page - 1) * pageSize;
      const res = await api.listTemplates({
        type: filterType === "all" ? undefined : filterType,
        limit: pageSize,
        offset,
      });
      setTemplates(res.templates);
      setTotal(res.total);
      setSelected(new Set());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterType]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const changeFilter = (t: TemplateType | "all") => {
    setFilterType(t);
    setPage(1);
  };

  const changePageSize = (ps: number) => {
    setPageSize(ps);
    setPage(1);
  };

  // 初始化预置
  const initPresets = async () => {
    setLoading(true);
    try {
      await api.initTemplatePresets();
      setPage(1);
      await loadTemplates();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "初始化失败");
    } finally {
      setLoading(false);
    }
  };

  // 新建
  const startCreate = () => {
    setEditing({ ...EMPTY_TEMPLATE });
    setShowForm(true);
  };

  // 编辑
  const startEdit = (tpl: PromptTemplate) => {
    setEditing({ ...tpl, slots: tpl.slots?.map((s) => ({ ...s })) || [] });
    setShowForm(true);
  };

  // 保存
  const saveTemplate = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      if (editing.id) {
        await api.updateTemplate(editing.id, editing);
      } else {
        await api.createTemplate(editing);
      }
      setShowForm(false);
      setEditing(null);
      await loadTemplates();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  // 单个删除
  const deleteTemplate = async (id: string) => {
    if (!confirm(t("templates.deleteConfirm"))) return;
    try {
      await api.deleteTemplate(id);
      await loadTemplates();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  // 批量删除
  const batchDelete = async () => {
    if (selected.size === 0) return;
    if (!confirm(t("templates.batchDeleteConfirm", { count: selected.size }))) return;
    setDeleting(true);
    try {
      await api.batchDeleteTemplates([...selected]);
      await loadTemplates();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "批量删除失败");
    } finally {
      setDeleting(false);
    }
  };

  // 全选/取消
  const toggleAll = () => {
    if (selected.size === templates.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(templates.map((t) => t.id)));
    }
  };

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // ===== 单条预览 =====

  const openPreview = (tpl: PromptTemplate) => {
    setPreviewTpl(tpl);
    setPreviewResult(null);
    // 初始化 slot 值为默认值
    const defaults: Record<string, string> = {};
    for (const s of tpl.slots ?? []) {
      if (s.default) defaults[s.name] = s.default;
    }
    setPreviewSlotValues(defaults);
  };

  const closePreview = () => {
    setPreviewTpl(null);
    setPreviewResult(null);
    setPreviewSlotValues({});
  };

  const doPreview = async () => {
    if (!previewTpl) return;
    setPreviewing(true);
    try {
      const res = await api.previewTemplate({
        template_ids: [previewTpl.id],
        slot_values: previewSlotValues,
      });
      setPreviewResult(res.final_prompt);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "预览失败");
    } finally {
      setPreviewing(false);
    }
  };

  // Slot 编辑 helper
  const updateSlot = (idx: number, field: keyof PromptSlot, value: string | string[]) => {
    if (!editing) return;
    const slots = [...editing.slots];
    slots[idx] = { ...slots[idx], [field]: value };
    setEditing({ ...editing, slots });
  };

  const addSlot = () => {
    if (!editing) return;
    setEditing({
      ...editing,
      slots: [
        ...editing.slots,
        { name: "", type: "input" as SlotType, label: "", default: "", options: [], placeholder: "" },
      ],
    });
  };

  const removeSlot = (idx: number) => {
    if (!editing) return;
    setEditing({ ...editing, slots: editing.slots.filter((_, i) => i !== idx) });
  };

  return (
    <div className="flex-1 overflow-auto px-6 py-5">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-txt-0">{t("templates.title")}</h1>
          <p className="text-sm text-txt-2 mt-1">{t("templates.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          {templates.length === 0 && total === 0 && (
            <button
              onClick={initPresets}
              disabled={loading}
              className="px-3 h-8 text-xs rounded-s border border-[var(--acc-soft)] text-[var(--acc)] hover:bg-[var(--acc-soft)] transition-colors"
            >
              {t("templates.initPresets")}
            </button>
          )}
          {selected.size > 0 && (
            <button
              onClick={batchDelete}
              disabled={deleting}
              className="px-3 h-8 text-xs rounded-s font-medium text-white transition-colors disabled:opacity-40"
              style={{ background: "var(--red)" }}
            >
              🗑 {t("common.batchDelete", "批量删除")} ({selected.size})
            </button>
          )}
          <button
            onClick={startCreate}
            className="px-3 h-8 text-xs rounded-s font-medium text-white transition-colors"
            style={{ background: "var(--acc)" }}
          >
            + {t("templates.create")}
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-3 px-3 py-2 text-xs rounded-s bg-[var(--red-soft)] text-[var(--red)] border border-[var(--red-soft)]">
          {error}
          <button className="ml-3 underline" onClick={() => setError(null)}>
            {t("common.cancel")}
          </button>
        </div>
      )}

      {/* 类型筛选 */}
      <div className="flex items-center gap-1 mb-3">
        {TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => changeFilter(opt.value)}
            className={`px-2.5 h-7 text-xs rounded-s transition-colors ${
              filterType === opt.value
                ? "bg-[var(--acc-soft)] text-[var(--acc)] font-medium"
                : "text-txt-1 hover:bg-bg-3"
            }`}
          >
            {opt.label}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-txt-2">
          {loading ? "…" : `${total} ${t("common.records", "条")}`}
        </span>
      </div>

      {/* 列表 */}
      {loading ? (
        <p className="text-sm text-txt-2">{t("common.loading")}</p>
      ) : templates.length === 0 ? (
        <div className="text-center py-16 text-txt-3">
          <p className="text-lg mb-2">📋</p>
          <p className="text-sm">{t("templates.empty")}</p>
        </div>
      ) : (
        <>
          {/* 全选 */}
          <div className="flex items-center gap-2 mb-2 px-1">
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                checked={selected.size === templates.length && templates.length > 0}
                onChange={toggleAll}
                className="w-3.5 h-3.5 rounded accent-[var(--acc)]"
              />
              <span className="text-[10px] text-txt-2">{t("common.selectAll")}</span>
            </label>
          </div>

          <div className="space-y-2">
            {templates.map((tpl) => (
              <div
                key={tpl.id}
                className={`flex items-start gap-3 p-3 rounded-s border bg-bg-1 transition-colors ${
                  selected.has(tpl.id)
                    ? "border-[var(--acc)] bg-[var(--acc-soft)]"
                    : "border-line hover:border-[var(--acc-soft)]"
                }`}
              >
                {/* 批量选择 */}
                <label className="pt-1 flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={selected.has(tpl.id)}
                    onChange={() => toggleOne(tpl.id)}
                    className="w-3.5 h-3.5 rounded accent-[var(--acc)]"
                  />
                </label>
                {/* 类型标签 */}
                <span
                  className="shrink-0 mt-0.5 px-1.5 py-0.5 text-[10px] rounded font-medium"
                  style={{
                    background: "var(--acc-soft)",
                    color: "var(--acc)",
                  }}
                >
                  {t(`templates.type.${tpl.type}`)}
                </span>
                {/* 内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-txt-0">{tpl.name}</span>
                    {tpl.slots && tpl.slots.length > 0 && (
                      <span className="text-[10px] text-txt-2">
                        {tpl.slots.length} Slots: {tpl.slots.map((s) => `{${s.name}}`).join(", ")}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-txt-2 mt-0.5 line-clamp-2">{tpl.text}</p>
                  {tpl.description && (
                    <p className="text-[10px] text-txt-3 mt-0.5">{tpl.description}</p>
                  )}
                </div>
                {/* 操作 */}
                <div className="shrink-0 flex items-center gap-1">
                  <button
                    onClick={() => openPreview(tpl)}
                    className="px-2 h-6 text-[10px] rounded-s text-[var(--acc)] border border-[var(--acc-soft)] hover:bg-[var(--acc-soft)] transition-colors"
                    title={t("templates.preview")}
                  >
                    🔍
                  </button>
                  <button
                    onClick={() => startEdit(tpl)}
                    className="px-2 h-6 text-[10px] rounded-s text-txt-1 hover:bg-bg-3 transition-colors"
                  >
                    {t("common.edit")}
                  </button>
                  <button
                    onClick={() => deleteTemplate(tpl.id)}
                    className="px-2 h-6 text-[10px] rounded-s text-[var(--red)] hover:bg-[var(--red-soft)] transition-colors"
                  >
                    {t("common.delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* 分页 */}
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-line">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-txt-2">{t("common.pageSize")}</span>
              <select
                value={pageSize}
                onChange={(e) => changePageSize(Number(e.target.value))}
                className="h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
              >
                {PAGE_SIZES.map((ps) => (
                  <option key={ps} value={ps}>{ps}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(1)}
                disabled={page <= 1}
                className="px-2 h-7 text-[10px] rounded-s border border-line text-txt-1 hover:bg-bg-3 disabled:opacity-30"
              >
                «
              </button>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-2 h-7 text-[10px] rounded-s border border-line text-txt-1 hover:bg-bg-3 disabled:opacity-30"
              >
                ‹
              </button>
              <span className="px-2 text-[10px] text-txt-1">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-2 h-7 text-[10px] rounded-s border border-line text-txt-1 hover:bg-bg-3 disabled:opacity-30"
              >
                ›
              </button>
              <button
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
                className="px-2 h-7 text-[10px] rounded-s border border-line text-txt-1 hover:bg-bg-3 disabled:opacity-30"
              >
                »
              </button>
            </div>
          </div>
        </>
      )}

      {/* ===== 单条预览弹出层 ===== */}
      {previewTpl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={closePreview}>
          <div
            className="w-[560px] max-h-[85vh] overflow-y-auto bg-bg-1 border border-line rounded-xl shadow-2xl p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-base font-semibold text-txt-0">{previewTpl.name}</h2>
                <span
                  className="inline-block mt-0.5 px-1.5 py-0.5 text-[10px] rounded font-medium"
                  style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
                >
                  {t(`templates.type.${previewTpl.type}`)}
                </span>
              </div>
              <button onClick={closePreview} className="px-2 h-7 text-xs rounded-s text-txt-2 hover:bg-bg-3">
                ✕
              </button>
            </div>

            {/* 模板文本 */}
            <div className="mb-3">
              <span className="text-[11px] text-txt-2 font-medium">{t("templates.fields.text")}</span>
              <pre className="mt-1 p-2 rounded-s border border-line bg-bg-1 text-[11px] text-txt-1 whitespace-pre-wrap break-all font-mono">
                {previewTpl.text}
              </pre>
              {previewTpl.description && (
                <p className="mt-1 text-[10px] text-txt-3">{previewTpl.description}</p>
              )}
            </div>

            {/* Slot 填写 */}
            {(previewTpl.slots?.length ?? 0) > 0 && (
              <div className="mb-3 space-y-2">
                <span className="text-[11px] text-txt-2 font-medium">{t("templates.slotValues")}</span>
                {previewTpl.slots.map((slot) => (
                  <div key={slot.name} className="flex items-center gap-2">
                    <label className="text-[10px] text-txt-2 w-24 shrink-0 truncate" title={slot.name}>
                      {slot.label || slot.name}
                    </label>
                    {slot.type === "dropdown" && slot.options.length > 0 ? (
                      <select
                        value={previewSlotValues[slot.name] || ""}
                        onChange={(e) => setPreviewSlotValues((v) => ({ ...v, [slot.name]: e.target.value }))}
                        className="flex-1 h-7 px-2 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                      >
                        <option value="">—</option>
                        {slot.options.map((o) => (
                          <option key={o} value={o}>{o}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        value={previewSlotValues[slot.name] || ""}
                        onChange={(e) => setPreviewSlotValues((v) => ({ ...v, [slot.name]: e.target.value }))}
                        placeholder={slot.placeholder || slot.default || ""}
                        className="flex-1 h-7 px-2 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* 操作按钮 */}
            <div className="flex items-center justify-end gap-2 mb-3 pt-3 border-t border-line">
              <button
                onClick={closePreview}
                className="px-3 h-7 text-xs rounded-s text-txt-1 hover:bg-bg-3"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={doPreview}
                disabled={previewing}
                className="px-4 h-7 text-xs rounded-s font-medium text-white transition-colors disabled:opacity-40"
                style={{ background: "var(--acc)" }}
              >
                {previewing ? "..." : "▶ 预览"}
              </button>
            </div>

            {/* 预览结果 */}
            {previewResult && (
              <div className="p-3 rounded-s border border-[var(--acc-soft)] bg-[var(--acc-soft)]">
                <span className="text-[10px] text-[var(--acc)] font-medium">{t("templates.previewResult")}</span>
                <pre className="mt-1 text-xs text-txt-1 whitespace-pre-wrap break-all font-mono">{previewResult}</pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 编辑弹窗 */}
      {showForm && editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-[640px] max-h-[80vh] overflow-y-auto bg-bg-1 border border-line rounded-xl shadow-2xl p-5">
            <h2 className="text-base font-semibold text-txt-0 mb-3">
              {editing.id ? t("templates.editTitle") : t("templates.createTitle")}
            </h2>

            {/* 名称 */}
            <label className="block text-[11px] text-txt-2 mb-1">{t("templates.fields.name")}</label>
            <input
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              className="w-full h-8 px-2 text-xs rounded-s border border-line bg-bg-1 text-txt-0 mb-3"
            />

            {/* 类型 */}
            <label className="block text-[11px] text-txt-2 mb-1">{t("templates.fields.type")}</label>
            <select
              value={editing.type}
              onChange={(e) => setEditing({ ...editing, type: e.target.value as TemplateType })}
              className="w-full h-8 px-2 text-xs rounded-s border border-line bg-bg-1 text-txt-0 mb-3"
            >
              {TYPE_OPTIONS.filter((o) => o.value !== "all").map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>

            {/* 模板文本 */}
            <label className="block text-[11px] text-txt-2 mb-1">{t("templates.fields.text")}</label>
            <textarea
              value={editing.text}
              onChange={(e) => setEditing({ ...editing, text: e.target.value })}
              placeholder={t("templates.fields.textPlaceholder")}
              rows={4}
              className="w-full px-2 py-1 text-xs rounded-s border border-line bg-bg-1 text-txt-0 mb-3 font-mono resize-y"
            />

            {/* 描述 */}
            <label className="block text-[11px] text-txt-2 mb-1">{t("templates.fields.description")}</label>
            <input
              value={editing.description}
              onChange={(e) => setEditing({ ...editing, description: e.target.value })}
              className="w-full h-8 px-2 text-xs rounded-s border border-line bg-bg-1 text-txt-0 mb-3"
            />

            {/* Slots */}
            <div className="flex items-center justify-between mb-2">
              <label className="text-[11px] text-txt-2">{t("templates.fields.slots")}</label>
              <button
                onClick={addSlot}
                className="px-2 h-5 text-[10px] rounded-s text-[var(--acc)] border border-[var(--acc-soft)] hover:bg-[var(--acc-soft)]"
              >
                + {t("templates.fields.addSlot")}
              </button>
            </div>
            {editing.slots.map((slot, idx) => (
              <div key={idx} className="mb-3 p-2 rounded-s border border-line bg-bg-1 space-y-1.5">
                <div className="flex items-center gap-2">
                  <input
                    value={slot.name}
                    onChange={(e) => updateSlot(idx, "name", e.target.value)}
                    placeholder={t("templates.fields.slotName")}
                    className="flex-1 h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                  />
                  <select
                    value={slot.type}
                    onChange={(e) => updateSlot(idx, "type", e.target.value)}
                    className="h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                  >
                    <option value="input">{slotTypeLabel("input", t)}</option>
                    <option value="dropdown">{slotTypeLabel("dropdown", t)}</option>
                  </select>
                  <button
                    onClick={() => removeSlot(idx)}
                    className="px-1.5 h-6 text-[10px] rounded-s text-[var(--red)] hover:bg-[var(--red-soft)]"
                  >
                    ×
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    value={slot.label}
                    onChange={(e) => updateSlot(idx, "label", e.target.value)}
                    placeholder={t("templates.fields.slotLabel")}
                    className="flex-1 h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                  />
                  <input
                    value={slot.default}
                    onChange={(e) => updateSlot(idx, "default", e.target.value)}
                    placeholder={t("templates.fields.slotDefault")}
                    className="w-24 h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                  />
                  <input
                    value={slot.placeholder}
                    onChange={(e) => updateSlot(idx, "placeholder", e.target.value)}
                    placeholder={t("templates.fields.slotPlaceholder")}
                    className="w-24 h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                  />
                </div>
                {slot.type === "dropdown" && (
                  <input
                    value={slot.options.join(", ")}
                    onChange={(e) =>
                      updateSlot(
                        idx,
                        "options",
                        e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                      )
                    }
                    placeholder={t("templates.fields.slotOptionsHint")}
                    className="w-full h-7 px-1.5 text-[10px] rounded-s border border-line bg-bg-1 text-txt-0"
                  />
                )}
              </div>
            ))}

            {/* 底部按钮 */}
            <div className="flex items-center justify-end gap-2 mt-3 pt-3 border-t border-line">
              <button
                onClick={() => {
                  setShowForm(false);
                  setEditing(null);
                }}
                className="px-3 h-8 text-xs rounded-s text-txt-1 hover:bg-bg-3"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={saveTemplate}
                disabled={saving || !editing.name.trim() || !editing.text.trim()}
                className="px-4 h-8 text-xs rounded-s font-medium text-white transition-colors disabled:opacity-40"
                style={{ background: "var(--acc)" }}
              >
                {saving ? t("common.loading") : t("common.save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

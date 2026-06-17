/**
 * 组件管理页面 — 独立管理界面
 *
 * 功能：
 * - 列出所有已注册的自定义组件
 * - 编辑凭据配置（API Key / Base URL / Model ID）
 * - 填写测试参数 → 校验 → 独立运行
 * - 查看运行结果
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AiOutlineLoading, AiOutlinePlayCircle, AiOutlineCheckCircle, AiOutlineCloseCircle } from "react-icons/ai";
import { FiExternalLink } from "react-icons/fi";
import { CollapsibleSection, groupPropertiesByUiGroup, getOrderedGroupNames } from "../../components/ui/CollapsibleSection";

/* ============================================================
   Type Helpers
   ============================================================ */

interface ComponentInfo {
  component_id: string;
  display_name: string;
  category: string;
  subcategory: string;
  description: string;
  version: string;
  output_type: string;
  credential_schema: CredentialSchema;
  input_schema: Record<string, PropertyDef>;
  input_required: string[];
}

interface CredentialSchema {
  type: string;
  properties: Record<string, PropertyDef>;
  required: string[];
}

interface PropertyDef {
  type: string;
  title: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  enumNames?: string[];
  minimum?: number;
  maximum?: number;
  step?: number;
  format?: string;
}

interface TestResult {
  success: boolean;
  outputs: { type: string; value: string }[] | null;
  error: string | null;
}

/* ============================================================
   Components
   ============================================================ */

/* ============================================================
   Category definitions for grouping
   ============================================================ */

const SUB_CATEGORIES: Record<string, { label: string; icon: string }> = {
  video: { label: "视频", icon: "🎬" },
  image: { label: "图片", icon: "🖼️" },
  default: { label: "其他", icon: "🧩" },
};

/* ============================================================
   Components
   ============================================================ */

export function ComponentsPage() {
  const { t } = useTranslation();
  const [components, setComponents] = useState<ComponentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSub, setActiveSub] = useState<string>("all");

  const fetchComponents = useCallback(async () => {
    try {
      const res = await fetch("/api/components/list");
      if (!res.ok) throw new Error("Failed to load");
      const data = await res.json();
      setComponents(data.components ?? []);
    } catch (e) {
      console.error("[ComponentsPage] fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchComponents();
  }, [fetchComponents]);

  // Group components by subcategory
  const grouped = components.reduce<Record<string, ComponentInfo[]>>((acc, comp) => {
    const key = comp.subcategory || "default";
    (acc[key] ??= []).push(comp);
    return acc;
  }, {});

  const groupKeys = Object.keys(grouped);
  const tabs = [
    { key: "all", label: `全部 (${components.length})`, icon: "📦" },
    ...groupKeys.map((k) => ({
      key: k,
      label: `${SUB_CATEGORIES[k]?.label || "其他"} (${grouped[k].length})`,
      icon: SUB_CATEGORIES[k]?.icon || "🧩",
    })),
  ];

  const filtered = activeSub === "all" ? components : grouped[activeSub] || [];

  return (
    <div className="h-full flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "var(--txt-0)" }}>
            {t("components.title")}
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--txt-3)" }}>
            {t("components.desc")}
          </p>
        </div>
        <span className="text-xs px-3 py-1 rounded-full" style={{ background: "var(--bg-2)", color: "var(--txt-2)" }}>
          {components.length} {t("common.noItems", "items")}
        </span>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--txt-2)" }}>
          <AiOutlineLoading className="animate-spin" />
          Loading...
        </div>
      ) : components.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          {/* Subcategory Tabs */}
          <div className="flex items-center gap-2 flex-wrap">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveSub(tab.key)}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition"
                style={{
                  borderColor: activeSub === tab.key ? "var(--acc)" : "var(--line)",
                  background: activeSub === tab.key ? "var(--acc-soft)" : "var(--bg-1)",
                  color: activeSub === tab.key ? "var(--acc)" : "var(--txt-2)",
                }}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </div>

          {activeSub === "all" ? (
            // All view: grouped by subcategory
            groupKeys.map((key) => (
              <div key={key}>
                <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--txt-1)" }}>
                  <span>{SUB_CATEGORIES[key]?.icon || "🧩"}</span>
                  <span>{SUB_CATEGORIES[key]?.label || "其他"}</span>
                  <span className="text-xs font-normal" style={{ color: "var(--txt-3)" }}>
                    ({grouped[key].length})
                  </span>
                </h2>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
                  {grouped[key].map((comp) => (
                    <ComponentCard key={comp.component_id} comp={comp} />
                  ))}
                </div>
              </div>
            ))
          ) : (
            // Single subcategory view
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {filtered.map((comp) => (
                <ComponentCard key={comp.component_id} comp={comp} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ============================================================
   Component Card
   ============================================================ */

function ComponentCard({ comp }: { comp: ComponentInfo }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="rounded-xl border overflow-hidden transition-all"
      style={{
        background: "var(--bg-1)",
        borderColor: "var(--line)",
      }}
    >
      {/* Card Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:brightness-110 transition"
        style={{ background: expanded ? "var(--bg-2)" : "transparent" }}
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">🎬</span>
          <div>
            <div className="text-sm font-semibold" style={{ color: "var(--txt-0)" }}>
              {comp.display_name}
            </div>
            <div className="text-[11px] flex items-center gap-2" style={{ color: "var(--txt-3)" }}>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ background: "var(--acc-soft)", color: "var(--acc)" }}>
                {comp.category}/{comp.subcategory || "general"}
              </span>
              <span>v{comp.version}</span>
              <span>·</span>
              <span>{comp.output_type}</span>
            </div>
          </div>
        </div>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          style={{
            color: "var(--txt-3)",
            transform: expanded ? "rotate(180deg)" : "none",
            transition: "transform 0.2s",
          }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-5 animate-in fade-in slide-in-from-top-2 duration-150">
          {/* Description */}
          {comp.description && (
            <p className="text-xs" style={{ color: "var(--txt-2)" }}>{comp.description}</p>
          )}

          {/* Credential Editor */}
          <CredentialSection comp={comp} />

          {/* Test Form */}
          <TestSection comp={comp} />
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Credential Section
   ============================================================ */

function CredentialSection({ comp }: { comp: ComponentInfo }) {
  const { t } = useTranslation();
  const credSchema = comp.credential_schema;

  if (!credSchema?.properties) return null;

  const [credentials, setCredentials] = useState<Record<string, string>>(() => {
    // 初始值：先用本地缓存填充默认值
    const saved = loadCredentials(comp.component_id);
    const defaults: Record<string, string> = {};
    Object.entries(credSchema.properties).forEach(([key, prop]) => {
      defaults[key] = saved?.[key] ?? String(prop.default ?? "");
    });
    return defaults;
  });
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  // 挂载时从服务端加载已持久化的凭据
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/components/${comp.component_id}/credentials`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.configured && data.credentials) {
          // 服务端有凭据 → 优先使用（反向同步到 localStorage）
          const serverCreds: Record<string, string> = {};
          Object.entries(credSchema.properties).forEach(([key, prop]) => {
            // 服务端返回的是遮蔽后的值，但我们需要明文
            // 服务端不返回明文，所以只更新有本地缓存的部分
            const localVal = loadCredentials(comp.component_id)?.[key];
            serverCreds[key] = localVal ?? String(prop.default ?? "");
          });
          // 保留本地已填写的值，标记为已配置
          setCredentials(serverCreds);
          setSaveStatus("saved");
        }
      })
      .catch(() => { /* 忽略加载错误 */ });
    return () => { cancelled = true; };
  }, [comp.component_id, credSchema.properties]);

  const handleChange = (key: string, value: string) => {
    const next = { ...credentials, [key]: value };
    setCredentials(next);
    saveCredentials(comp.component_id, next);
    if (saveStatus === "saved") setSaveStatus("idle");
  };

  const handleSave = async () => {
    setSaveStatus("saving");
    try {
      const res = await fetch(`/api/components/${comp.component_id}/credentials`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credentials }),
      });
      if (!res.ok) throw new Error("保存失败");
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch {
      setSaveStatus("error");
    }
  };

  // 按 ui:group 分组凭据属性
  const credGroups = useMemo(() => groupPropertiesByUiGroup(credSchema.properties), [credSchema.properties]);
  const hasGroups = credGroups.size > 1;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold flex items-center gap-2" style={{ color: "var(--txt-2)" }}>
          <span className="w-1 h-3 rounded-full" style={{ background: "var(--amber)" }} />
          {t("components.credential")}
        </h3>
        <button
          type="button"
          onClick={handleSave}
          disabled={saveStatus === "saving"}
          className="text-[10px] px-3 py-1 rounded-md border font-medium transition disabled:opacity-50"
          style={{
            borderColor: saveStatus === "saved" ? "var(--green)" : "var(--acc)",
            color: saveStatus === "saved" ? "var(--green)" : "var(--acc)",
            background: saveStatus === "saved" ? "rgba(34,197,94,0.08)" : "var(--acc-soft)",
          }}
        >
          {saveStatus === "saving"
            ? t("common.saving", "保存中...")
            : saveStatus === "saved"
            ? t("common.saved", "已保存 ✓")
            : saveStatus === "error"
            ? t("common.saveError", "保存失败")
            : t("common.save", "保存到服务端")}
        </button>
      </div>
      {hasGroups ? (
        <div className="space-y-2">
          {getOrderedGroupNames(credGroups).map((groupName) => {
            const entries = credGroups.get(groupName) || [];
            return (
              <CollapsibleSection key={groupName} title={groupName} count={entries.length} defaultOpen={groupName === "基础参数"}>
                <div className="space-y-3">
                  {entries.map(([key, prop]) => (
                    <div key={key}>
                      <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--txt-2)" }}>
                        {prop.title || key}
                      </label>
                      <input
                        type={prop.format === "password" ? "password" : "text"}
                        value={credentials[key] ?? ""}
                        onChange={(e) => handleChange(key, e.target.value)}
                        className="w-full px-3 py-2 rounded-lg text-xs font-mono border transition focus:outline-none"
                        style={{
                          background: "var(--bg-0)",
                          borderColor: "var(--line)",
                          color: "var(--txt-0)",
                        }}
                        placeholder={prop.description || key}
                      />
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3">
          {Object.entries(credSchema.properties).map(([key, prop]) => (
            <div key={key}>
              <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--txt-2)" }}>
                {prop.title || key}
              </label>
              <input
                type={prop.format === "password" ? "password" : "text"}
                value={credentials[key] ?? ""}
                onChange={(e) => handleChange(key, e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-xs font-mono border transition focus:outline-none"
                style={{
                  background: "var(--bg-0)",
                  borderColor: "var(--line)",
                  color: "var(--txt-0)",
                }}
                placeholder={prop.description || key}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Test Section
   ============================================================ */

function TestSection({ comp }: { comp: ComponentInfo }) {
  const { t } = useTranslation();
  const [params, setParams] = useState<Record<string, unknown>>(() => {
    const defaults: Record<string, unknown> = {};
    Object.entries(comp.input_schema).forEach(([key, prop]) => {
      if (prop.default !== undefined) {
        defaults[key] = prop.default;
      }
    });
    return defaults;
  });

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [validateMsg, setValidateMsg] = useState<string | null>(null);

  const handleParamChange = (key: string, value: unknown) => {
    setParams((prev) => ({ ...prev, [key]: value }));
    setValidateMsg(null);
  };

  const handleValidate = async () => {
    try {
      const saved = loadCredentials(comp.component_id);
      const inputs: Record<string, unknown> = {};
      if (params.prompt) inputs.prompt = params.prompt;
      if (params.image_url) inputs.image_url = params.image_url;
      if (params.image) inputs.image = params.image;

      const res = await fetch(`/api/components/${comp.component_id}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs, params }),
      });
      const data = await res.json();
      setValidateMsg(data.valid ? "valid" : data.errors?.[0] || data.error || "invalid");
    } catch (e) {
      setValidateMsg(`请求失败: ${e}`);
    }
  };

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    try {
      const saved = loadCredentials(comp.component_id);
      const inputs: Record<string, unknown> = {};
      if (params.prompt) inputs.prompt = params.prompt;
      if (params.image_url) inputs.image_url = params.image_url;
      if (params.image) inputs.image = params.image;

      const res = await fetch(`/api/components/${comp.component_id}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs, params, credentials: saved }),
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setResult({ success: false, outputs: null, error: String(e) });
    } finally {
      setRunning(false);
    }
  };

  const inputSchema = comp.input_schema;
  const mode = (params.duration_mode as string) || "seconds";

  // 随机种子生成
  const randomizeSeed = () => {
    handleParamChange("seed", Math.floor(Math.random() * 9_000_000_000) + 1_000_000_000);
  };

  // 按时长模式过滤并构建分组用的 schema
  const filteredSchema = useMemo(() => {
    const result: Record<string, PropertyDef> = {};
    Object.entries(inputSchema).forEach(([key, prop]) => {
      if (key === "duration_seconds" && mode !== "seconds") return;
      if (key === "duration_frames" && mode !== "frames") return;
      result[key] = prop;
    });
    return result;
  }, [inputSchema, mode]);

  const visibleEntries = useMemo(() => Object.entries(filteredSchema), [filteredSchema]);

  // 按 ui:group 分组
  const inputGroups = useMemo(() => groupPropertiesByUiGroup(filteredSchema), [filteredSchema]);
  const hasInputGroups = inputGroups.size > 1;

  return (
    <div>
      <h3 className="text-xs font-semibold mb-3 flex items-center gap-2" style={{ color: "var(--txt-2)" }}>
        <span className="w-1 h-3 rounded-full" style={{ background: "var(--cyan)" }} />
        {t("components.testForm")}
      </h3>

      {/* Form Fields — grouped if ui:group is present */}
      {hasInputGroups ? (
        <div className="space-y-2 mb-4">
          {getOrderedGroupNames(inputGroups).map((groupName) => {
            const entries = inputGroups.get(groupName) || [];
            return (
              <CollapsibleSection key={groupName} title={groupName} count={entries.length} defaultOpen={groupName === "基础参数"}>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {entries.map(([key, prop]) => (
                    <div key={key} className={key === "prompt" || key === "image_url" ? "sm:col-span-2" : ""}>
                      <FormField
                        name={key}
                        prop={prop}
                        value={params[key]}
                        onChange={(v) => handleParamChange(key, v)}
                        extra={
                          key === "seed" ? (
                            <button
                              type="button"
                              onClick={randomizeSeed}
                              className="text-[10px] px-2 py-0.5 rounded border transition hover:brightness-110 shrink-0"
                              style={{
                                borderColor: "var(--line)",
                                color: "var(--txt-2)",
                                background: "var(--bg-2)",
                              }}
                              title="随机生成 10 位种子值"
                            >
                              随机
                            </button>
                          ) : undefined
                        }
                      />
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            );
          })}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          {visibleEntries.map(([key, prop]) => (
            <div key={key} className={key === "prompt" || key === "image_url" ? "sm:col-span-2" : ""}>
              <FormField
                name={key}
                prop={prop}
                value={params[key]}
                onChange={(v) => handleParamChange(key, v)}
                extra={
                  key === "seed" ? (
                    <button
                      type="button"
                      onClick={randomizeSeed}
                      className="text-[10px] px-2 py-0.5 rounded border transition hover:brightness-110 shrink-0"
                      style={{
                        borderColor: "var(--line)",
                        color: "var(--txt-2)",
                        background: "var(--bg-2)",
                      }}
                      title="随机生成 10 位种子值"
                    >
                      随机
                    </button>
                  ) : undefined
                }
              />
            </div>
          ))}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={handleValidate}
          className="px-4 py-2 rounded-lg text-xs font-medium border transition"
          style={{
            borderColor: "var(--line)",
            color: "var(--txt-1)",
            background: "var(--bg-2)",
          }}
        >
          {t("components.validate")}
        </button>

        <button
          type="button"
          onClick={handleRun}
          disabled={running}
          className="px-5 py-2 rounded-lg text-xs font-semibold transition flex items-center gap-2 disabled:opacity-50"
          style={{
            background: "var(--acc)",
            color: "#fff",
          }}
        >
          {running ? (
            <>
              <AiOutlineLoading className="animate-spin" />
              {t("components.running")}
            </>
          ) : (
            <>
              <AiOutlinePlayCircle />
              {t("components.run")}
            </>
          )}
        </button>
      </div>

      {/* Validation Message */}
      {validateMsg && (
        <div
          className={`mt-3 text-xs px-3 py-2 rounded-lg flex items-center gap-2 ${
            validateMsg === "valid" ? "bg-green-900/20 text-green-400" : "bg-red-900/20 text-red-400"
          }`}
          style={validateMsg === "valid"
            ? { background: "rgba(34,197,94,0.1)", color: "var(--green)" }
            : { background: "rgba(239,68,68,0.1)", color: "var(--red)" }}
        >
          {validateMsg === "valid" ? <AiOutlineCheckCircle /> : <AiOutlineCloseCircle />}
          {validateMsg === "valid" ? t("components.valid") : validateMsg}
        </div>
      )}

      {/* Result Display */}
      {result && (
        <div className="mt-3">
          <h4 className="text-[11px] font-semibold mb-2" style={{ color: "var(--txt-2)" }}>
            {t("components.result")}
          </h4>
          <div
            className="rounded-lg p-3 space-y-2"
            style={{
              background: result.success ? "rgba(34,197,94,0.06)" : "rgba(239,68,68,0.06)",
              border: `1px solid ${result.success ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
            }}
          >
            <div className="flex items-center gap-2 text-xs font-medium" style={{
              color: result.success ? "var(--green)" : "var(--red)",
            }}>
              {result.success ? <AiOutlineCheckCircle /> : <AiOutlineCloseCircle />}
              {result.success ? t("components.success") : t("components.failed")}
            </div>

            {result.error && (
              <p className="text-xs font-mono break-all" style={{ color: "var(--txt-3)" }}>
                {result.error}
              </p>
            )}

            {result.outputs && result.outputs.length > 0 && result.outputs.map((output, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-mono shrink-0"
                  style={{ background: "var(--bg-2)", color: "var(--txt-2)" }}
                >
                  {output.type}
                </span>
                {output.type === "video_url" ? (
                  <a
                    href={output.value}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-400 underline break-all flex items-center gap-1"
                  >
                    <FiExternalLink className="shrink-0" />
                    {output.value.length > 80 ? output.value.slice(0, 80) + "..." : output.value}
                  </a>
                ) : output.type === "asset_id" ? (
                  <span className="flex items-center gap-1" style={{ color: "var(--txt-1)" }}>
                    <AiOutlineCheckCircle className="text-green-400 shrink-0" />
                    <span className="font-mono">{output.value}</span>
                    <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>
                      (已存入素材库)
                    </span>
                  </span>
                ) : (
                  <span className="break-all" style={{ color: "var(--txt-1)" }}>
                    {output.value}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Form Field Renderer
   ============================================================ */

function FormField({
  name,
  prop,
  value,
  onChange,
  extra,
}: {
  name: string;
  prop: PropertyDef;
  value: unknown;
  onChange: (v: unknown) => void;
  extra?: React.ReactNode;
}) {
  if (prop.type === "boolean") {
    return (
      <div className="flex items-center justify-between px-3 py-2 rounded-lg border" style={{ borderColor: "var(--line)", background: "var(--bg-0)" }}>
        <label className="text-xs" style={{ color: "var(--txt-2)" }}>{prop.title || name}</label>
        <button
          type="button"
          onClick={() => onChange(!value)}
          className={`w-9 h-5 rounded-full transition relative ${value ? "bg-green-500" : "bg-gray-600"}`}
        >
          <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition ${value ? "left-4" : "left-0.5"}`} />
        </button>
      </div>
    );
  }

  if (prop.enum) {
    return (
      <div>
        <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--txt-2)" }}>{prop.title || name}</label>
        <select
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 rounded-lg text-xs border transition focus:outline-none"
          style={{
            background: "var(--bg-0)",
            borderColor: "var(--line)",
            color: "var(--txt-0)",
          }}
        >
          {prop.enum.map((opt, i) => (
            <option key={opt} value={opt}>
              {prop.enumNames?.[i] ?? opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  // 数字类型（带范围）→ 滑块 + 数字输入
  if ((prop.type === "integer" || prop.type === "number") && prop.minimum !== undefined && prop.maximum !== undefined) {
    const min = Number(prop.minimum);
    const max = Number(prop.maximum);
    const step = prop.step ?? 1;
    const val = Number(value ?? prop.default ?? min);

    return (
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] font-medium" style={{ color: "var(--txt-2)" }}>
            {prop.title || name}
          </label>
          <div className="flex items-center gap-1">
            <input
              type="number"
              value={val}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (!isNaN(v)) onChange(Math.max(min, Math.min(max, v)));
              }}
              min={min}
              max={max}
              step={step}
              className="w-16 px-2 py-0.5 rounded text-xs font-mono text-center border transition focus:outline-none"
              style={{
                background: "var(--bg-0)",
                borderColor: "var(--line)",
                color: "var(--txt-0)",
              }}
            />
            {extra}
          </div>
        </div>
        <input
          type="range"
          value={val}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min}
          max={max}
          step={step}
          className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
          style={{
            accentColor: "var(--acc)",
            background: "var(--bg-2)",
          }}
        />
        <div className="flex justify-between mt-0.5">
          <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>{min}</span>
          <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>{max}</span>
        </div>
      </div>
    );
  }

  if (prop.type === "integer" || prop.type === "number") {
    return (
      <div>
        <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--txt-2)" }}>
          {prop.title || name}
          {prop.minimum !== undefined && prop.maximum !== undefined && (
            <span className="ml-1 text-[10px]" style={{ color: "var(--txt-3)" }}>
              ({prop.minimum}-{prop.maximum})
            </span>
          )}
        </label>
        <div className="flex items-center gap-1">
          <input
            type="number"
            value={value as number}
            onChange={(e) => onChange(e.target.value ? Number(e.target.value) : 0)}
            min={prop.minimum}
            max={prop.maximum}
            className="flex-1 px-3 py-2 rounded-lg text-xs font-mono border transition focus:outline-none"
            style={{
              background: "var(--bg-0)",
              borderColor: "var(--line)",
              color: "var(--txt-0)",
            }}
          />
          {extra}
        </div>
      </div>
    );
  }

  // Default: string/text input
  return (
    <div>
      <label className="block text-[11px] font-medium mb-1" style={{ color: "var(--txt-2)" }}>{prop.title || name}</label>
      <input
        type="text"
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 rounded-lg text-xs font-mono border transition focus:outline-none"
        style={{
          background: "var(--bg-0)",
          borderColor: "var(--line)",
          color: "var(--txt-0)",
        }}
        placeholder={prop.description || name}
      />
    </div>
  );
}

/* ============================================================
   Local Storage Helpers
   ============================================================ */

const CRED_KEY_PREFIX = "sf:comp-cred:";

function loadCredentials(componentId: string): Record<string, string> | null {
  try {
    const raw = localStorage.getItem(CRED_KEY_PREFIX + componentId);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveCredentials(componentId: string, creds: Record<string, string>) {
  try {
    localStorage.setItem(CRED_KEY_PREFIX + componentId, JSON.stringify(creds));
  } catch {
    // silently fail
  }
}

/* ============================================================
   Empty State
   ============================================================ */

function EmptyState() {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-col items-center justify-center py-20 text-center"
      style={{ color: "var(--txt-3)" }}
    >
      <span className="text-4xl mb-3 opacity-30">🧩</span>
      <p className="text-sm">{t("components.noComponents")}</p>
      <p className="text-xs mt-1 opacity-60">
        请先在 src/spriteflow/components/ 下创建组件并注册
      </p>
    </div>
  );
}

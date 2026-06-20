import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { useConfirm } from "@/components/ui/Confirm";
import { Pagination } from "@/components/ui/Pagination";
import { FaPlus } from "react-icons/fa";
import { IoImageOutline } from "react-icons/io5";
import { IoVideocamOutline } from "react-icons/io5";
import { AiOutlineAudio } from "react-icons/ai";
import { TfiText } from "react-icons/tfi";

interface WorkflowItem {
  id: string;
  name: string;
  description?: string;
  category?: string;
  node_count?: number;
  created_at?: string;
  updated_at?: string;
  is_published?: boolean;
  is_template?: boolean;
}

interface PresetItem {
  id: string;
  title: string;
  description?: string;
  icon?: string;
  image?: string;
  node_count?: number;
  edge_count?: number;
}

const PRESET_ICON_MAP: Record<string, React.ReactNode> = {
  plus: <FaPlus size={18} />,
  image: <IoImageOutline size={18} />,
  video: <IoVideocamOutline size={18} />,
  audio: <AiOutlineAudio size={18} />,
  text: <TfiText size={18} />,
};

type TabKey = "my-workflows" | "presets";

export function WorkflowListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const PAGE_SIZE = 12;
  const [tab, setTab] = useState<TabKey>("my-workflows");

  // ---- Workflows ----
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [offset, setOffset] = useState(0);

  // ---- Presets ----
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(false);

  const loadWorkflows = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await axios.get("/api/workflow/get-workflow-defs", {
        params: { limit: PAGE_SIZE, offset },
      });
      const data = res.data;
      if (Array.isArray(data)) {
        setWorkflows(data);
        setTotal(data.length);
      } else {
        setWorkflows(data?.workflows || []);
        setTotal(data?.total || 0);
      }
    } catch (err: any) {
      console.error("Failed to load workflows", err);
      setError(err?.response?.data?.detail || err?.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  const loadPresets = useCallback(async () => {
    try {
      setPresetsLoading(true);
      const res = await axios.get("/api/workflow/presets");
      setPresets(res.data || []);
    } catch (err: any) {
      console.error("Failed to load presets", err);
    } finally {
      setPresetsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkflows();
  }, [loadWorkflows]);

  useEffect(() => {
    if (tab === "presets") {
      loadPresets();
    }
  }, [tab, loadPresets]);

  const handleCreate = async () => {
    try {
      const res = await axios.post("/api/workflow/create", {
        name: t("workflow.newWorkflow", "New Workflow"),
        description: "",
        data: {
          nodes: [],
          edges: [],
        },
      });
      const newId = res.data?.id || res.data?.workflow_id;
      if (newId) {
        navigate(`/workflow/${newId}`);
      } else {
        loadWorkflows();
      }
    } catch (err: any) {
      console.error("Failed to create workflow", err);
    }
  };

  const handleUsePreset = async (presetId: string) => {
    if (presetId === "empty-workflow") {
      handleCreate();
      return;
    }
    try {
      const presetRes = await axios.get(`/api/workflow/presets/${presetId}`);
      const preset = presetRes.data;

      // Convert ReactFlow format → API format expected by processWorkflowData
      const convertNode = (node: any) => {
        const typeMap: Record<string, string> = {
          textNode: "text",
          imageNode: "image",
          videoNode: "video",
          audioNode: "audio",
          concatNode: "utility",
          vidConcatNode: "utility",
        };
        const category = typeMap[node.type] || node.type?.replace("Node", "") || "text";
        const model = node.data?.selectedModel?.id || "";
        const input_params = node.data?.formValues || {};
        const output_params = {
          resultUrl: node.data?.resultUrl ?? null,
          outputs: node.data?.outputs || [],
        };
        return {
          id: node.id,
          category,
          model,
          input_params,
          output_params,
          position: node.position || { x: 0, y: 0 },
        };
      };

      const convertedNodes = (preset.nodes || []).map(convertNode);
      const convertedEdges = (preset.edges || []).map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle || null,
        targetHandle: e.targetHandle || null,
      }));

      const createRes = await axios.post("/api/workflow/create", {
        name: preset.title || t("workflow.newWorkflow", "New Workflow"),
        description: preset.description || "",
        data: {
          nodes: convertedNodes,
          edges: convertedEdges,
        },
        edges: convertedEdges,
      });
      const newId = createRes.data?.id || createRes.data?.workflow_id;
      if (newId) {
        navigate(`/workflow/${newId}`);
      }
    } catch (err: any) {
      console.error("Failed to create from preset", err);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    const ok = await confirm({
      title: t("workflow.deleteTitle", "Delete Workflow"),
      message: t("workflow.deleteConfirm", { name }),
      okText: t("common.delete"),
      variant: "danger",
    });
    if (!ok) return;
    try {
      await axios.delete(`/api/workflow/delete-workflow-def/${id}`);
      loadWorkflows();
    } catch (err: any) {
      console.error("Failed to delete workflow", err);
    }
  };

  const handleDuplicate = async (id: string, name: string) => {
    try {
      const res = await axios.post(`/api/workflow/${id}/duplicate`, {
        name: `${name} (Copy)`,
      });
      loadWorkflows();
      const newId = res.data?.workflow_id;
      if (newId) {
        navigate(`/workflow/${newId}`);
      }
    } catch (err: any) {
      console.error("Failed to duplicate workflow", err);
    }
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setOffset(0);
  };

  const filtered = workflows.filter((w) =>
    !searchQuery ||
    w.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    w.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // ---- Render helpers ----
  const TABS: { key: TabKey; label: string }[] = [
    { key: "my-workflows", label: t("workflow.myWorkflows", "My Workflows") },
    { key: "presets", label: t("workflow.presetTemplates", "Preset Templates") },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--line-soft)]">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--txt-0)" }}>
            {t("workflow.title", "AI Workflow")}
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--txt-3)" }}>
            {t("workflow.subtitle", "Create and manage AI workflow pipelines")}
          </p>
        </div>
        <button
          onClick={handleCreate}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2"
          style={{
            background: "var(--acc)",
            color: "#fff",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          {t("workflow.create", "Create Workflow")}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-[var(--line-soft)]">
        {TABS.map((tItem) => (
          <button
            key={tItem.key}
            onClick={() => { setTab(tItem.key); setOffset(0); }}
            className="px-5 py-2.5 text-sm font-medium transition-colors relative"
            style={{
              color: tab === tItem.key ? "var(--acc)" : "var(--txt-2)",
              borderBottom: tab === tItem.key ? "2px solid var(--acc)" : "2px solid transparent",
              marginBottom: -1,
            }}
          >
            {tItem.label}
          </button>
        ))}
      </div>

      {/* Search bar (only for workflows) */}
      {tab === "my-workflows" && (
        <div className="px-6 py-3 border-b border-[var(--line-soft)]">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder={t("workflow.searchPlaceholder", "Search workflows...")}
            className="w-full max-w-md px-3 py-2 rounded-lg text-sm outline-none border"
            style={{
              background: "var(--bg-2)",
              color: "var(--txt-0)",
              borderColor: "var(--line)",
            }}
          />
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* ===== My Workflows ===== */}
        {tab === "my-workflows" && (
          <>
            {loading ? (
              <div className="flex items-center justify-center h-32">
                <div className="text-sm" style={{ color: "var(--txt-3)" }}>
                  {t("common.loading", "Loading...")}
                </div>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-32 gap-2">
                <div className="text-sm text-red-500">{t("common.error", "Error")}</div>
                <div className="text-xs" style={{ color: "var(--txt-3)" }}>{error}</div>
                <button
                  onClick={loadWorkflows}
                  className="px-3 py-1 rounded text-xs"
                  style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
                >
                  {t("common.refresh", "Retry")}
                </button>
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 gap-3">
                <div className="text-sm" style={{ color: "var(--txt-3)" }}>
                  {searchQuery
                    ? t("workflow.searchEmpty", "No matching workflows")
                    : t("workflow.empty", "No workflows yet")}
                </div>
                {!searchQuery && (
                  <button
                    onClick={handleCreate}
                    className="px-4 py-2 rounded-lg text-sm font-medium"
                    style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
                  >
                    {t("workflow.create", "Create your first workflow")}
                  </button>
                )}
              </div>
            ) : (
              <>
                <div className="text-xs mb-4" style={{ color: "var(--txt-3)" }}>
                  {t("workflow.totalCount", "{{total}} workflows total", { total })}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {filtered.map((w) => (
                    <div
                      key={w.id}
                      className="rounded-xl border p-4 cursor-pointer transition-all hover:shadow-lg group"
                      style={{
                        background: "var(--bg-2)",
                        borderColor: "var(--line)",
                      }}
                      onClick={() => navigate(`/workflow/${w.id}`)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <h3
                            className="text-sm font-semibold truncate"
                            style={{ color: "var(--txt-0)" }}
                          >
                            {w.name || t("workflow.untitled", "Untitled")}
                          </h3>
                          {w.description && (
                            <p
                              className="text-xs mt-1 line-clamp-2"
                              style={{ color: "var(--txt-2)" }}
                            >
                              {w.description}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 mt-3">
                        {w.is_published && (
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full"
                            style={{
                              background: "rgba(34,197,94,0.15)",
                              color: "#22c55e",
                            }}
                          >
                            {t("workflow.published", "Published")}
                          </span>
                        )}
                        {w.is_template && (
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full"
                            style={{
                              background: "rgba(59,130,246,0.15)",
                              color: "#3b82f6",
                            }}
                          >
                            {t("workflow.template", "Template")}
                          </span>
                        )}
                        {w.category && (
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full"
                            style={{
                              background: "var(--bg-3)",
                              color: "var(--txt-2)",
                            }}
                          >
                            {w.category}
                          </span>
                        )}
                        {w.node_count !== undefined && (
                          <span
                            className="text-[10px] ml-auto"
                            style={{ color: "var(--txt-3)" }}
                          >
                            {w.node_count} {t("workflow.nodes", "nodes")}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--line-soft)]">
                        <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>
                          {w.updated_at
                            ? new Date(w.updated_at).toLocaleDateString()
                            : w.created_at
                              ? new Date(w.created_at).toLocaleDateString()
                              : ""}
                        </span>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDuplicate(w.id, w.name);
                            }}
                            className="text-[10px] px-2 py-1 rounded hover:bg-blue-500/10"
                            style={{ color: "var(--txt-3)" }}
                            title={t("workflow.duplicate", "Duplicate")}
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                            </svg>
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(w.id, w.name);
                            }}
                            className="text-[10px] px-2 py-1 rounded hover:bg-red-500/10"
                            style={{ color: "var(--txt-3)" }}
                            title={t("common.delete", "Delete")}
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {total > PAGE_SIZE && (
                  <div className="mt-6">
                    <Pagination
                      total={total}
                      limit={PAGE_SIZE}
                      offset={offset}
                      onChange={setOffset}
                    />
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ===== Preset Templates ===== */}
        {tab === "presets" && (
          <>
            {presetsLoading ? (
              <div className="flex items-center justify-center h-32">
                <div className="text-sm" style={{ color: "var(--txt-3)" }}>
                  {t("common.loading", "Loading...")}
                </div>
              </div>
            ) : presets.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 gap-3">
                <div className="text-sm" style={{ color: "var(--txt-3)" }}>
                  {t("workflow.noPresets", "No preset templates available")}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {presets.map((preset) => (
                  <div
                    key={preset.id}
                    className="rounded-xl border p-4 cursor-pointer transition-all hover:shadow-lg group"
                    style={{
                      background: "var(--bg-2)",
                      borderColor: "var(--line)",
                    }}
                    onClick={() => handleUsePreset(preset.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span style={{ color: "var(--acc)" }}>
                            {PRESET_ICON_MAP[preset.icon || "plus"] || <FaPlus size={18} />}
                          </span>
                          <h3
                            className="text-sm font-semibold truncate"
                            style={{ color: "var(--txt-0)" }}
                          >
                            {preset.title}
                          </h3>
                        </div>
                        {preset.description && (
                          <p
                            className="text-xs mt-1 line-clamp-2"
                            style={{ color: "var(--txt-2)" }}
                          >
                            {preset.description}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 mt-3">
                      <span
                        className="text-[10px] px-2 py-0.5 rounded-full"
                        style={{
                          background: "rgba(59,130,246,0.15)",
                          color: "#3b82f6",
                        }}
                      >
                        {t("workflow.preset", "Preset")}
                      </span>
                      {preset.node_count !== undefined && (
                        <span
                          className="text-[10px] ml-auto"
                          style={{ color: "var(--txt-3)" }}
                        >
                          {preset.node_count} {t("workflow.nodes", "nodes")}
                          {preset.edge_count !== undefined && (
                            <> · {preset.edge_count} edges</>
                          )}
                        </span>
                      )}
                    </div>

                    {preset.image && (
                      <div className="mt-3 h-24 rounded-lg overflow-hidden">
                        <img
                          src={preset.image}
                          alt={preset.title}
                          className="w-full h-full object-cover opacity-60 group-hover:opacity-90 transition-opacity"
                        />
                      </div>
                    )}

                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-[var(--line-soft)]">
                      <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>
                        {preset.id === "empty-workflow"
                          ? t("workflow.startFresh", "Start from scratch")
                          : t("workflow.usePreset", "Click to use this template")}
                      </span>
                      <span
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] px-2 py-1 rounded"
                        style={{
                          background: "var(--acc-soft)",
                          color: "var(--acc)",
                        }}
                      >
                        {t("workflow.use", "Use")} →
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

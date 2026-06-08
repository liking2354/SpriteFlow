import { useState, useCallback, useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { ReactFlowProvider } from "@xyflow/react";
import { api } from "@/api/client";
import { PipelineCanvas } from "@/components/graph/PipelineCanvas";
import { NodePalette } from "@/components/graph/NodePalette";
import { RunSummary } from "@/components/graph/RunSummary";
import { ExecutionLog } from "@/components/graph/ExecutionLog";
import { PresetPipelines } from "@/components/graph/PresetPipelines";
import { Button } from "@/components/ui/Button";
import { useGraphRun } from "@/components/graph/useGraphRun";
import type { PipelineGraphModel, PipelineNodeParams } from "@/api/types";

function newEmptyGraph(): PipelineGraphModel {
  return {
    id: "",
    name: "",
    description: "",
    spec_id: null,
    nodes: [],
    edges: [],
    tags: [],
  };
}

function generateId(): string {
  return `g-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function GraphEditorPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { graphId } = useParams<{ graphId: string }>();
  const isNew = !graphId || graphId === "new";

  const { runState, run, rerun, runSingleNode, reset, restoreLatestRun } = useGraphRun();

  const [graph, setGraph] = useState<PipelineGraphModel>(newEmptyGraph());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [graphName, setGraphName] = useState("");
  const [graphDesc, setGraphDesc] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [showBackground, setShowBackground] = useState(true);
  const [showRunSummary, setShowRunSummary] = useState(false);
  const [summaryDismissed, setSummaryDismissed] = useState(false);
  const [previewNodeId, setPreviewNodeId] = useState<string | null>(null);

  // 加载已有图
  useEffect(() => {
    if (!isNew && graphId) {
      api.getGraph(graphId).then((g) => {
        setGraph(g);
        setGraphName(g.name);
        setGraphDesc(g.description);
        setSavedId(g.id);
        // 恢复最近一次运行结果，让 ImageViewer 等展示节点显示上次产出
        restoreLatestRun(graphId);
      }).catch((e) => {
        console.error("Load graph failed", e);
        navigate("/graphs", { replace: true });
      });
    }
  }, [isNew, graphId, navigate, restoreLatestRun]);

  const handleGraphChange = useCallback((g: PipelineGraphModel) => {
    setGraph((prev) => ({
      ...g,
      id: prev.id,
      name: prev.name,
      description: prev.description,
      spec_id: prev.spec_id,
      tags: prev.tags,
    }));
  }, []);

  const handleNodeSelect = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
  }, []);

  const handleNodeParamsChange = useCallback(
    (nodeId: string, params: PipelineNodeParams) => {
      setGraph((prev) => ({
        ...prev,
        nodes: prev.nodes.map((n) =>
          n.id === nodeId ? { ...n, params } : n
        ),
      }));
    },
    []
  );

  const handleNodeCollapsedChange = useCallback(
    (nodeId: string, collapsed: boolean) => {
      setGraph((prev) => ({
        ...prev,
        nodes: prev.nodes.map((n) =>
          n.id === nodeId
            ? { ...n, collapsed, ui: { ...((n.ui as Record<string, unknown>) ?? {}), collapsed } }
            : n
        ),
      }));
    },
    []
  );

  // 保存/更新
  const handleSave = useCallback(async () => {
    if (!graphName.trim()) return;
    setIsSaving(true);
    try {
      const g: PipelineGraphModel = {
        ...graph,
        id: savedId ?? generateId(),
        name: graphName,
        description: graphDesc,
      };
      if (savedId) {
        await api.updateGraph(savedId, g);
      } else {
        await api.createGraph(g);
        setSavedId(g.id);
        // 新建后更新 URL
        navigate(`/graphs/${g.id}/edit`, { replace: true });
      }
    } catch (e) {
      console.error("Save graph failed", e);
    } finally {
      setIsSaving(false);
    }
  }, [graph, graphName, graphDesc, savedId, navigate]);

  // 运行（自动保存）
  const handleRun = useCallback(async () => {
    if (graph.nodes.length === 0) return;

    let graphToRun = graph;
    if (!savedId && graphName.trim()) {
      try {
        const g: PipelineGraphModel = {
          ...graph,
          id: generateId(),
          name: graphName,
          description: graphDesc,
        };
        await api.createGraph(g);
        setSavedId(g.id);
        graphToRun = g;
        navigate(`/graphs/${g.id}/edit`, { replace: true });
      } catch (e) {
        console.error("Auto-save before run failed", e);
      }
    }

    await run(graphToRun);
  }, [graph, graphName, graphDesc, savedId, run, navigate]);

  const handleRerun = useCallback(async (nodeId: string, mode?: string) => {
    // 已有运行记录 → 尝试使用 rerun 重跑
    if (runState.runId) {
      try {
        await rerun(runState.runId, nodeId, mode);
        return;
      } catch (e: any) {
        console.warn("Rerun node failed, falling back to cold-start:", e?.message);
        // 中断重连 SSE（如果 rerun 部分失败导致残留）
        reset();
      }
    }
    // 冷启动：runId 为空或 rerun 失败 → 创建新运行，仅执行此节点
    try {
      await runSingleNode(savedId, nodeId);
    } catch (e) {
      console.error("Run single node failed", e);
    }
  }, [runState.runId, rerun, runSingleNode, savedId, reset]);

  const handleThumbnailClick = useCallback((nodeId: string) => {
    setPreviewNodeId(nodeId);
  }, []);

  // 解析预览节点 ID → 实际 config 节点 ID（display 节点需要映射）
  const previewConfigNodeId = useMemo(() => {
    if (!previewNodeId) return null;
    // 在图中查找是否 display 节点
    const node = graph.nodes.find((n) => n.id === previewNodeId);
    if (node && (node.type === "ImageViewer" || node.type === "GalleryViewer")) {
      const fromUi = (node.ui as Record<string, unknown> | undefined)?.["config_node_id"] as string;
      if (fromUi) return fromUi;
      // 如果 ui 中 config_node_id 为空，从入边自动推导
      const incomingEdge = graph.edges.find(e => e.dst_node === previewNodeId);
      if (incomingEdge) return incomingEdge.src_node;
      return null;
    }
    return previewNodeId;
  }, [previewNodeId, graph.nodes, graph.edges]);
  const previewUrl = previewConfigNodeId
    ? runState.nodeStatuses[previewConfigNodeId]?.url ?? null
    : null;

  // 返回列表
  const handleBack = useCallback(() => {
    navigate("/graphs");
  }, [navigate]);

  const runCompletedEffect = runState.graphStatus === "completed" || runState.graphStatus === "failed";
  const effectiveShowSummary = !summaryDismissed && (showRunSummary || (runCompletedEffect && runState.runSummary !== null && !runState.isRunning));

  // 新运行开始时重置关闭状态
  useEffect(() => {
    if (runState.isRunning) {
      setSummaryDismissed(false);
      setShowRunSummary(false);
    }
  }, [runState.isRunning]);

  // 加载预设管线
  const handleLoadPreset = useCallback((presetGraph: PipelineGraphModel) => {
    setGraph((prev) => ({
      ...prev,
      nodes: presetGraph.nodes,
      edges: presetGraph.edges,
      tags: presetGraph.tags ?? prev.tags,
    }));
    setGraphName(presetGraph.name || "");
    setGraphDesc(presetGraph.description || "");
    setSavedId(null);
    setSelectedNodeId(null);
  }, []);

  const statusBarMessage = runState.isRunning
    ? t("graph.runningGraph", "正在执行管线图...")
    : runState.graphStatus === "completed"
      ? t("graph.runDone", "执行完成")
      : runState.graphStatus === "failed"
        ? `⚠ ${runState.error ?? t("graph.runFailed", "执行失败")}`
        : null;

  const nodeLabels = useMemo(
    () => Object.fromEntries(graph.nodes.map((n) => [n.id, n.type])),
    [graph.nodes]
  );

  return (
    <div className="flex h-full">
      {/* 左侧：节点面板 + 执行日志 */}
      <div
        className="w-[220px] shrink-0 border-r flex flex-col"
        style={{ borderColor: "var(--line)", background: "var(--bg-1)" }}
      >
        <NodePalette />
        <div className="flex-1 min-h-0">
          <ExecutionLog
            nodeStatuses={runState.nodeStatuses}
            nodeLabels={nodeLabels}
            isRunning={runState.isRunning}
          />
        </div>
      </div>

      {/* 中间/右侧：画布全高 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 工具栏 */}
        <div
          className="flex items-center gap-3 px-4 py-2 border-b shrink-0"
          style={{ borderColor: "var(--line)", background: "var(--bg-1)" }}
        >
          <Button size="sm" variant="ghost" onClick={handleBack}>
            ← {t("graph.backToList", "返回列表")}
          </Button>
          <PresetPipelines onLoad={handleLoadPreset} />
          <input
            type="text"
            className="w-44 h-8 px-2.5 rounded-lg text-[12px] bg-bg-0 border border-[var(--line)] text-txt-0 focus:outline-none focus:ring-1 focus:ring-[var(--acc)]"
            placeholder={t("graph.namePlaceholder", "图名称...")}
            value={graphName}
            onChange={(e) => setGraphName(e.target.value)}
          />
          <input
            type="text"
            className="flex-1 h-8 px-2.5 rounded-lg text-[12px] bg-bg-0 border border-[var(--line)] text-txt-0 focus:outline-none focus:ring-1 focus:ring-[var(--acc)]"
            placeholder={t("graph.descPlaceholder", "描述（可选）...")}
            value={graphDesc}
            onChange={(e) => setGraphDesc(e.target.value)}
          />
          <div className="flex items-center gap-1">
            <ToggleButton active={showBackground} onClick={() => setShowBackground((v) => !v)}>{t("graph.grid")}</ToggleButton>
            <ToggleButton active={showControls} onClick={() => setShowControls((v) => !v)}>{t("graph.controls")}</ToggleButton>
            <ToggleButton active={showMiniMap} onClick={() => setShowMiniMap((v) => !v)}>{t("graph.map")}</ToggleButton>
          </div>
          <Button size="sm" onClick={handleSave} loading={isSaving}>
            {savedId ? t("graph.update", "更新") : t("common.save")}
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={handleRun}
            disabled={graph.nodes.length === 0 || runState.isRunning}
            loading={runState.isRunning}
          >
            {runState.isRunning
              ? t("common.running")
              : t("graph.run", "▶ 运行")}
          </Button>
        </div>

        {/* 运行状态栏 */}
        {statusBarMessage && (
          <div
            className="flex items-center gap-2 px-4 py-1.5 text-[11px] border-b shrink-0"
            style={{
              background: runState.isRunning
                ? "rgba(59,130,246,0.08)"
                : runState.graphStatus === "completed"
                  ? "rgba(16,185,129,0.08)"
                  : "rgba(239,68,68,0.08)",
              borderColor: "var(--line-soft)",
              color: runState.isRunning
                ? "var(--blue, #3b82f6)"
                : runState.graphStatus === "completed"
                  ? "var(--green, #10b981)"
                  : "var(--red, #ef4444)",
            }}
          >
            {runState.isRunning && (
              <span className="spinner shrink-0" />
            )}
            <span>{statusBarMessage}</span>
            {runState.runId && (
              <span
                className="ml-auto text-[10px] font-mono opacity-60"
                style={{ color: "var(--txt-3)" }}
              >
                #{runState.runId}
              </span>
            )}
            {runCompletedEffect && runState.runSummary && (
              <button
                type="button"
                onClick={() => setShowRunSummary((v) => !v)}
                className="px-2 py-0.5 rounded text-[10px] border transition-colors"
                style={{
                  borderColor: "var(--acc)",
                  color: "var(--acc)",
                  background: "rgba(99,102,241,0.10)",
                }}
              >
                {showRunSummary
                  ? t("graph.hideSummary", "关闭摘要")
                  : t("graph.viewSummary", "查看摘要")}
              </button>
            )}
          </div>
        )}

        {/* 画布 — 全高 */}
        <div className="flex-1 min-h-0">
          <ReactFlowProvider>
            <PipelineCanvas
              graph={graph}
              onChange={handleGraphChange}
              onSelectNode={handleNodeSelect}
              selectedNodeId={selectedNodeId}
              nodeStatuses={runState.nodeStatuses}
              onNodeParamsChange={handleNodeParamsChange}
              onCollapsedChange={handleNodeCollapsedChange}
              showMiniMap={showMiniMap}
              showControls={showControls}
              showBackground={showBackground}
              onSaveShortcut={handleSave}
              onRunShortcut={handleRun}
              onRerunNode={handleRerun}
              onThumbnailClick={handleThumbnailClick}
              initialViewport={
                graph.viewport && typeof (graph.viewport as Record<string, unknown>).zoom === "number"
                  ? graph.viewport as { x: number; y: number; zoom: number }
                  : null
              }
            />
          </ReactFlowProvider>
        </div>

        {/* 运行摘要面板 */}
        {effectiveShowSummary && (
          <RunSummary
            summary={runState.runSummary}
            duration={runState.runDuration}
            onClose={() => { setShowRunSummary(false); setSummaryDismissed(true); }}
            onNodeClick={(nodeId) => setPreviewNodeId(nodeId)}
          />
        )}

        {/* 全尺寸图片预览弹窗 */}
        {previewUrl && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 cursor-pointer"
            onClick={() => setPreviewNodeId(null)}
          >
            <div className="relative max-w-[90vw] max-h-[90vh]">
              <img
                src={previewUrl}
                alt={`${previewConfigNodeId} output`}
                className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
              />
              <button
                type="button"
                className="absolute top-2 right-2 w-8 h-8 flex items-center justify-center rounded-full bg-black/60 text-white text-lg hover:bg-black/80"
                onClick={() => setPreviewNodeId(null)}
              >
                ×
              </button>
              <div className="absolute bottom-2 left-2 px-2 py-1 rounded text-[11px] bg-black/60 text-white/80">
                {previewConfigNodeId}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ToggleButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-7 px-2 rounded-md text-[10px] border transition-colors"
      style={{
        borderColor: active ? "var(--acc)" : "var(--line)",
        color: active ? "var(--acc)" : "var(--txt-3)",
        background: active ? "rgba(99,102,241,0.10)" : "transparent",
      }}
    >
      {children}
    </button>
  );
}

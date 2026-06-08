import { useState, useCallback, useRef, useEffect } from "react";
import { api, subscribeGraphRunStream } from "@/api/client";
import type { PipelineGraphModel, GraphRunSummary, GraphRerunResponse } from "@/api/types";

export type NodeRunStatus = "idle" | "pending" | "queued" | "running" | "completed" | "failed";

/** 纯前端展示节点 — 不在后端执行，不应参与 nodeStatuses 初始化 */
const DISPLAY_NODE_TYPES = new Set(["ImageViewer", "GalleryViewer"]);

/** PipelineCanvas 兼容的状态格式 */
export interface CanvasNodeStatus {
  status: string;
  thumbnail?: string | null;
  error?: string | null;
  assetId?: string | null;
  url?: string | null;
  cacheHit?: boolean;
  /** 节点执行耗时（秒），来自 SSE duration 字段 */
  duration?: number;
  /** 节点类型（如 direction_variant, text2img） */
  nodeType?: string;
  /** 执行输入快照（prompt/params/template_ids 等） */
  inputs?: Record<string, unknown> | null;
}

export interface GraphRunState {
  isRunning: boolean;
  runId: string | null;
  /** PipelineCanvas 兼容的节点状态（可直接传给画布） */
  nodeStatuses: Record<string, CanvasNodeStatus>;
  graphStatus: NodeRunStatus;
  error: string | null;
  /** 运行完成后的摘要信息 */
  runSummary: GraphRunSummary | null;
  /** 运行耗时（秒） */
  runDuration: number;
}

export interface UseGraphRunReturn {
  runState: GraphRunState;
  run: (graph: PipelineGraphModel) => Promise<void>;
  /** 按已保存的 graph_id 运行（自动加载图 → 执行 → SSE 订阅） */
  runById: (graphId: string) => Promise<void>;
  rerun: (runId: string, nodeId: string, mode?: string) => Promise<GraphRerunResponse>;
  /** 冷启动执行单个节点（不需要先运行全图） */
  runSingleNode: (graphId: string, nodeId: string) => Promise<void>;
  reset: () => void;
  /** 从 DB 恢复图的最近一次运行结果（页面重进时调用） */
  restoreLatestRun: (graphId: string) => Promise<void>;
}

/**
 * 管线图执行 Hook
 *
 * 管理全图运行状态、SSE 订阅、节点缩略图收集
 */
export function useGraphRun(): UseGraphRunReturn {
  const [state, setState] = useState<GraphRunState>({
    isRunning: false,
    runId: null,
    nodeStatuses: {},
    graphStatus: "idle",
    error: null,
    runSummary: null,
    runDuration: 0,
  });

  // SSE 清理函数
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  const reset = useCallback(() => {
    cleanupRef.current?.();
    setState({
      isRunning: false,
      runId: null,
      nodeStatuses: {},
      graphStatus: "idle",
      error: null,
      runSummary: null,
      runDuration: 0,
    });
  }, []);

  const run = useCallback(async (graph: PipelineGraphModel) => {
    await _startRun(graph, () => api.runGraph({ graph }));
  }, []);

  /** 按已保存的 graph_id 运行管线图（先加载图再执行） */
  const runById = useCallback(async (graphId: string) => {
    const graph = await api.getGraph(graphId);
    await _startRun(graph, () => api.runGraphById(graphId));
  }, []);

  /** 内部：初始化状态 → 发起运行 → SSE 订阅 */
  const _startRun = useCallback(
    async (graph: PipelineGraphModel, execute: () => Promise<{ runId: string }>) => {
      if (graph.nodes.length === 0) return;

      // 初始化：仅业务节点 → pending（展示节点不执行，由 PipelineCanvas 通过 configNodeId 映射获取状态）
      const initStatuses: Record<string, CanvasNodeStatus> = {};
      graph.nodes.forEach((n) => {
        if (DISPLAY_NODE_TYPES.has(n.type)) return;
        initStatuses[n.id] = { status: "pending", thumbnail: null };
      });

      setState({
        isRunning: true,
        runId: null,
        nodeStatuses: initStatuses,
        graphStatus: "running",
        error: null,
        runSummary: null,
        runDuration: 0,
      });

      try {
        const result = await execute();
        const rid = result.runId;

        setState((prev) => ({
          ...prev,
          runId: rid,
        }));

        // SSE 订阅进度
        const unsubscribe = subscribeGraphRunStream(
          rid,
          (evt) => {
            setState((prev) => {
              switch (evt.type) {
                case "run_started":
                  return prev;

                case "node_queued":
                  if (evt.nodeId && prev.nodeStatuses[evt.nodeId]) {
                    return {
                      ...prev,
                      nodeStatuses: {
                        ...prev.nodeStatuses,
                        [evt.nodeId]: {
                          status: "queued",
                          thumbnail: prev.nodeStatuses[evt.nodeId].thumbnail,
                        },
                      },
                    };
                  }
                  return prev;

                case "node_started":
                  if (evt.nodeId && prev.nodeStatuses[evt.nodeId]) {
                    return {
                      ...prev,
                      nodeStatuses: {
                        ...prev.nodeStatuses,
                        [evt.nodeId]: {
                          status: "running",
                          thumbnail: prev.nodeStatuses[evt.nodeId].thumbnail,
                        },
                      },
                    };
                  }
                  return prev;

                case "node_completed": {
                  if (!evt.nodeId) return prev;
                  const existing = prev.nodeStatuses[evt.nodeId];
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "completed",
                        thumbnail: evt.thumbnail ?? existing?.thumbnail ?? null,
                        assetId: evt.assetId ?? existing?.assetId ?? null,
                        url: evt.url ?? existing?.url ?? null,
                        cacheHit: (evt as any).cacheHit ?? existing?.cacheHit,
                        duration: (evt as any).duration ?? existing?.duration,
                        nodeType: (evt as any).nodeType ?? existing?.nodeType,
                        inputs: (evt as any).inputs ?? existing?.inputs,
                      },
                    },
                  };
                }

                case "node_failed":
                  if (evt.nodeId) {
                    return {
                      ...prev,
                      nodeStatuses: {
                        ...prev.nodeStatuses,
                        [evt.nodeId]: {
                          status: "failed",
                          thumbnail: prev.nodeStatuses[evt.nodeId]?.thumbnail ?? null,
                          error: evt.error ?? null,
                        },
                      },
                    };
                  }
                  return prev;

                case "run_completed":
                  return {
                    ...prev,
                    isRunning: false,
                    graphStatus: "completed",
                    runSummary: evt.summary ?? prev.runSummary,
                    runDuration: evt.summary?.duration ?? prev.runDuration,
                  };

                case "run_failed":
                  return {
                    ...prev,
                    isRunning: false,
                    graphStatus: "failed",
                    error: evt.message ?? "运行失败",
                  };

                default:
                  return prev;
              }
            });
          },
          () => {
            setState((prev) => ({
              ...prev,
              isRunning: false,
              graphStatus: prev.graphStatus === "running" ? "failed" : prev.graphStatus,
              error: "SSE 连接断开",
            }));
          }
        );

        cleanupRef.current = unsubscribe;
      } catch (e: any) {
        setState((prev) => ({
          ...prev,
          isRunning: false,
          graphStatus: "failed",
          error: e?.message ?? "执行失败",
        }));
      }
    },
    []
  );

  /** 冷启动执行单个节点（不需要先运行全图） */
  const runSingleNode = useCallback(async (graphId: string, nodeId: string) => {
    // 关闭旧的 SSE 连接
    cleanupRef.current?.();
    cleanupRef.current = null;

    // 先加载图获取节点类型信息
    let graph: PipelineGraphModel;
    try {
      graph = await api.getGraph(graphId);
    } catch (e: any) {
      setState((prev) => ({
        ...prev,
        isRunning: false,
        error: "加载管线图失败",
      }));
      return;
    }

    // 初始化：仅目标节点 → pending
    const initStatuses: Record<string, CanvasNodeStatus> = {
      [nodeId]: { status: "pending", thumbnail: null },
    };

    setState({
      isRunning: true,
      runId: null,
      nodeStatuses: initStatuses,
      graphStatus: "running",
      error: null,
      runSummary: null,
      runDuration: 0,
    });

    try {
      const result = await api.runGraphNode(graphId, nodeId);
      const rid = result.runId;

      setState((prev) => ({
        ...prev,
        runId: rid,
      }));

      // SSE 订阅（复用同一事件处理逻辑）
      const unsubscribe = subscribeGraphRunStream(
        rid,
        (evt) => {
          setState((prev) => {
            switch (evt.type) {
              case "run_started":
                return prev;

              case "node_queued":
                if (evt.nodeId && prev.nodeStatuses[evt.nodeId]) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "queued",
                        thumbnail: prev.nodeStatuses[evt.nodeId].thumbnail,
                      },
                    },
                  };
                }
                // 新节点（如子图中产生的新节点）也加入
                if (evt.nodeId) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: { status: "queued", thumbnail: null },
                    },
                  };
                }
                return prev;

              case "node_started":
                if (evt.nodeId && prev.nodeStatuses[evt.nodeId]) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "running",
                        thumbnail: prev.nodeStatuses[evt.nodeId].thumbnail,
                      },
                    },
                  };
                }
                return prev;

              case "node_completed": {
                if (!evt.nodeId) return prev;
                const existing = prev.nodeStatuses[evt.nodeId];
                return {
                  ...prev,
                  nodeStatuses: {
                    ...prev.nodeStatuses,
                    [evt.nodeId]: {
                      status: "completed",
                      thumbnail: evt.thumbnail ?? existing?.thumbnail ?? null,
                      assetId: evt.assetId ?? existing?.assetId ?? null,
                      url: evt.url ?? existing?.url ?? null,
                      cacheHit: (evt as any).cacheHit ?? existing?.cacheHit,
                      duration: (evt as any).duration ?? existing?.duration,
                      nodeType: (evt as any).nodeType ?? existing?.nodeType,
                      inputs: (evt as any).inputs ?? existing?.inputs,
                    },
                  },
                };
              }

              case "node_failed":
                if (evt.nodeId) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "failed",
                        thumbnail: prev.nodeStatuses[evt.nodeId]?.thumbnail ?? null,
                        error: evt.error ?? null,
                      },
                    },
                  };
                }
                return prev;

              case "run_completed":
                return {
                  ...prev,
                  isRunning: false,
                  graphStatus: "completed",
                  runSummary: evt.summary ?? prev.runSummary,
                  runDuration: evt.summary?.duration ?? prev.runDuration,
                };

              case "run_failed":
                return {
                  ...prev,
                  isRunning: false,
                  graphStatus: "failed",
                  error: evt.message ?? "运行失败",
                };

              default:
                return prev;
            }
          });
        },
        () => {
          setState((prev) => ({
            ...prev,
            isRunning: false,
            graphStatus: prev.graphStatus === "running" ? "failed" : prev.graphStatus,
            error: "SSE 连接断开",
          }));
        }
      );

      cleanupRef.current = unsubscribe;
    } catch (e: any) {
      setState((prev) => ({
        ...prev,
        isRunning: false,
        graphStatus: "failed",
        error: e?.message ?? "执行失败",
      }));
    }
  }, []);

  /** 重新运行指定节点（改为 SSE 实时推送版本） */
  const rerunFn = useCallback(async (runId: string, nodeId: string, mode = "node_and_downstream") => {
    // 关闭旧的 SSE 连接
    cleanupRef.current?.();
    cleanupRef.current = null;

    // 将目标节点状态重置为 pending
    setState((prev) => {
      const updated = { ...prev.nodeStatuses };
      if (updated[nodeId]) {
        updated[nodeId] = { status: "pending", thumbnail: null };
      }
      return {
        ...prev,
        isRunning: true,
        graphStatus: "running",
        nodeStatuses: updated,
      };
    });

    try {
      const result = await api.rerunGraphNode(runId, nodeId, mode);

      // 订阅 SSE 获取实时进度（与 full run 同模式）
      const unsubscribe = subscribeGraphRunStream(
        runId,
        (evt) => {
          setState((prev) => {
            switch (evt.type) {
              case "node_queued":
                if (evt.nodeId && prev.nodeStatuses[evt.nodeId]) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "queued",
                        thumbnail: prev.nodeStatuses[evt.nodeId].thumbnail,
                      },
                    },
                  };
                }
                return prev;

              case "node_started":
                if (evt.nodeId && prev.nodeStatuses[evt.nodeId]) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "running",
                        thumbnail: prev.nodeStatuses[evt.nodeId].thumbnail,
                      },
                    },
                  };
                }
                return prev;

              case "node_completed": {
                if (!evt.nodeId) return prev;
                const existing = prev.nodeStatuses[evt.nodeId];
                return {
                  ...prev,
                  nodeStatuses: {
                    ...prev.nodeStatuses,
                    [evt.nodeId]: {
                      status: "completed",
                      thumbnail: evt.thumbnail ?? existing?.thumbnail ?? null,
                      assetId: evt.assetId ?? existing?.assetId ?? null,
                      url: evt.url ?? existing?.url ?? null,
                      cacheHit: (evt as any).cacheHit ?? existing?.cacheHit,
                      duration: (evt as any).duration ?? existing?.duration,
                    },
                  },
                };
              }

              case "node_failed":
                if (evt.nodeId) {
                  return {
                    ...prev,
                    nodeStatuses: {
                      ...prev.nodeStatuses,
                      [evt.nodeId]: {
                        status: "failed",
                        thumbnail: prev.nodeStatuses[evt.nodeId]?.thumbnail ?? null,
                        error: evt.error ?? null,
                      },
                    },
                  };
                }
                return prev;

              case "run_completed":
                return {
                  ...prev,
                  isRunning: false,
                  graphStatus: "completed",
                  runSummary: evt.summary ?? prev.runSummary,
                  runDuration: evt.summary?.duration ?? prev.runDuration,
                };

              case "run_failed":
                return {
                  ...prev,
                  isRunning: false,
                  graphStatus: "failed",
                  error: evt.message ?? "重跑失败",
                };

              default:
                return prev;
            }
          });
        },
        () => {
          setState((prev) => ({
            ...prev,
            isRunning: false,
            graphStatus: prev.graphStatus === "running" ? "failed" : prev.graphStatus,
            error: "SSE 连接断开",
          }));
        }
      );

      cleanupRef.current = unsubscribe;
      return result as unknown as GraphRerunResponse;
    } catch (e: any) {
      setState((prev) => ({
        ...prev,
        isRunning: false,
        graphStatus: "failed",
        error: e?.message ?? "重跑失败",
      }));
      throw e;
    }
  }, []);

  /** 从 DB 恢复图的最近一次运行结果，填充 nodeStatuses */
  const restoreLatestRun = useCallback(async (graphId: string) => {
    try {
      const data = await api.getGraphLatestRunResults(graphId);
      console.log("[restoreLatestRun] API response:", graphId, JSON.stringify({ runId: data.runId, status: data.status, nodeIds: Object.keys(data.nodeResults || {}) }));
      if (!data.runId || !data.nodeResults || Object.keys(data.nodeResults).length === 0) {
        console.log("[restoreLatestRun] No previous run results found for", graphId);
        return;
      }

      const statuses: Record<string, CanvasNodeStatus> = {};
      for (const [nid, nr] of Object.entries(data.nodeResults)) {
        statuses[nid] = {
          status: nr.status,
          thumbnail: nr.thumbnail ?? null,
          error: nr.error ?? null,
          assetId: nr.assetId ?? null,
          url: nr.url ?? null,
          cacheHit: (nr as any).cacheHit,
          duration: (nr as any).duration,
          nodeType: (nr as any).nodeType,
          inputs: (nr as any).inputs ?? null,
        };
      }

      console.log("[restoreLatestRun] Restoring nodeStatuses:", Object.keys(statuses), "first entry:", Object.values(statuses)[0]);
      setState((prev) => ({
        ...prev,
        runId: data.runId,
        nodeStatuses: statuses,
        graphStatus: (data.status as NodeRunStatus) ?? "completed",
      }));
    } catch (err) {
      console.error("[restoreLatestRun] Failed to restore run results:", err);
    }
  }, []);

  return { runState: state, run, runById, rerun: rerunFn, runSingleNode, reset, restoreLatestRun };
}

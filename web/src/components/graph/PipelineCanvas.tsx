import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Node,
  type Edge,
  type OnConnect,
  type Connection,
  type NodeChange,
  type EdgeChange,
  MarkerType,
  getIncomers,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTranslation } from "react-i18next";
import { BusinessNode, type BusinessNodeData } from "./BusinessNode";
import type {
  PipelineGraphModel,
  PipelineNodeModel,
  PipelineNodeParams,
  GraphEdgeModel,
  NodeSchema,
} from "@/api/types";
import { api } from "@/api/client";
import { useQuery } from "@tanstack/react-query";

const NODE_TYPES = { business: BusinessNode };

const NODE_DEFAULTS: Record<string, Partial<PipelineNodeParams>> = {
  CharacterMaster: { template_ids: "", slot_values: {}, size: "2k" },
  DirectionVariant: { template_ids: "", slot_values: {}, size: "2k" },
  AnimationSprite: { template_ids: "", slot_values: {}, max_images: 1, size: "2k" },
  SkillVFX: { template_ids: "", slot_values: {}, size: "2k" },
  ImageFusion: { template_ids: "", slot_values: {} },
};

interface PipelineCanvasProps {
  graph: PipelineGraphModel | null;
  onChange: (graph: PipelineGraphModel) => void;
  onSelectNode: (nodeId: string | null) => void;
  selectedNodeId: string | null;
  nodeStatuses: Record<
    string,
    { status: string; thumbnail?: string | null; error?: string | null; asset_id?: string | null; url?: string | null }
  >;
  /** 节点参数变更回调 */
  onNodeParamsChange?: (nodeId: string, params: PipelineNodeParams) => void;
  /** 节点折叠状态变更回调 */
  onCollapsedChange?: (nodeId: string, collapsed: boolean) => void;
  /** 初始视口状态（加载图时恢复） */
  initialViewport?: { x: number; y: number; zoom: number } | null;
  showMiniMap?: boolean;
  showControls?: boolean;
  showBackground?: boolean;
  onSaveShortcut?: () => void;
  onRunShortcut?: () => void;
  /** 重新运行指定节点（可选 mode: node_and_downstream|node_only|downstream_only） */
  onRerunNode?: (nodeId: string, mode?: string) => void;
}

let _globalNodeCounter = 0;

function defaultsFromSchema(schema?: NodeSchema): Partial<PipelineNodeParams> {
  if (!schema) return {};
  return Object.fromEntries(
    schema.params
      .filter((p) => p.default !== undefined && p.default !== null)
      .map((p) => [p.name, p.default])
  ) as Partial<PipelineNodeParams>;
}

function graphKey(g: PipelineGraphModel): string {
  const paramsHash = g.nodes.map((n) => `${n.id}:${JSON.stringify(n.params)}`).join("|");
  return `${g.id}|${g.nodes.map((n) => `${n.id}:${n.x},${n.y}:${(n.ui as Record<string, unknown> | undefined)?.["config_node_id"] ?? ""}`).join(";")}|${g.edges.map((e) => e.id).join(";")}|p:${paramsHash}`;
}

export function PipelineCanvas({
  graph,
  onChange,
  onSelectNode,
  selectedNodeId,
  nodeStatuses,
  onNodeParamsChange,
  onCollapsedChange,
  initialViewport,
  showMiniMap = true,
  showControls = true,
  showBackground = true,
  onSaveShortcut,
  onRunShortcut,
  onRerunNode,
}: PipelineCanvasProps) {
  const { t } = useTranslation();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useReactFlow();
  const [rfNodes, setRfNodes] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges] = useEdgesState<Edge>([]);
  const [searchState, setSearchState] = useState<{ open: boolean; x: number; y: number; query: string }>({ open: false, x: 0, y: 0, query: "" });
  const [contextMenu, setContextMenu] = useState<{ open: boolean; x: number; y: number; nodeId?: string | null; edgeId?: string | null }>({ open: false, x: 0, y: 0, nodeId: null, edgeId: null });
  const [edgeType, setEdgeType] = useState<"straight" | "smoothstep" | "bezier">("smoothstep");
  const clipboardRef = useRef<Node[]>([]);
  const schemasQuery = useQuery({
    queryKey: ["node-schemas", "pipeline"],
    queryFn: () => api.listNodesByCategory("pipeline"),
    staleTime: 60_000,
  });
  const nodeSchemas = useMemo(() => schemasQuery.data ?? [], [schemasQuery.data]);
  const schemaByType = useMemo(() => {
    return Object.fromEntries(nodeSchemas.map((s) => [s.type, s])) as Record<string, NodeSchema>;
  }, [nodeSchemas]);

  // ==== Refs for stale-closure prevention ====
  const lastGraphKeyRef = useRef("");
  const graphRef = useRef<PipelineGraphModel | null>(null);
  graphRef.current = graph;
  const rfNodesRef = useRef<Node[]>([]);
  const rfEdgesRef = useRef<Edge[]>([]);
  rfNodesRef.current = rfNodes;
  rfEdgesRef.current = rfEdges;
  const selectedNodeIdRef = useRef<string | null>(null);
  selectedNodeIdRef.current = selectedNodeId;
  // 稳定化 onNodeParamsChange（避免每次渲染重建 callback 造成节点重建）
  const onNodeParamsChangeRef = useRef(onNodeParamsChange);
  onNodeParamsChangeRef.current = onNodeParamsChange;
  // 稳定化 onCollapsedChange
  const onCollapsedChangeRef = useRef(onCollapsedChange);
  onCollapsedChangeRef.current = onCollapsedChange;
  // viewport 缓存
  const viewportRef = useRef<{ x: number; y: number; zoom: number }>({ x: 0, y: 0, zoom: 1 });
  // 是否已应用初始 viewport
  const viewportAppliedRef = useRef(false);
  // nodeStatuses 引用（用于 graph-build 效果中直接注入已有状态，避免时序依赖）
  const nodeStatusesRef = useRef(nodeStatuses);
  nodeStatusesRef.current = nodeStatuses;
  // 已在 graph-build 中应用过 nodeStatuses 的 graphKey（避免 nodeStatuses 效果做多余操作）
  const appliedStatusesKeyRef = useRef("");

  // 稳定化的参数变更回调 — 不会被 graph 变化导致的节点重建所影响
  const stableParamChange = useCallback(
    (nodeId: string, params: Record<string, unknown>) => {
      // 立即更新 React Flow 节点数据（不等待 graph 重渲染）
      setRfNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          const data = n.data as unknown as BusinessNodeData;
          return { ...n, data: { ...data, params } };
        })
      );
      // 通知父组件
      onNodeParamsChangeRef.current?.(nodeId, params as PipelineNodeParams);
    },
    [setRfNodes]
  );

  // 稳定化的折叠状态变更回调
  const stableCollapsedChange = useCallback(
    (nodeId: string, collapsed: boolean) => {
      setRfNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          const data = n.data as unknown as BusinessNodeData;
          return { ...n, data: { ...data, collapsed, ui: { ...(data.ui as Record<string, unknown> ?? {}), collapsed } } };
        })
      );
      onCollapsedChangeRef.current?.(nodeId, collapsed);
    },
    [setRfNodes]
  );

  // ===== Effect: graph 结构变化 → ReactFlow state =====
  useEffect(() => {
    if (!graph) return;
    const key = graphKey(graph);
    if (lastGraphKeyRef.current === key) return;
    lastGraphKeyRef.current = key;

    // 过滤掉旧版展示节点（ImageViewer / GalleryViewer），预览已内置到业务节点中
    const displayTypeSet = new Set(["ImageViewer", "GalleryViewer"]);
    const displayNodeIds = new Set(graph.nodes.filter(n => displayTypeSet.has(n.type)).map(n => n.id));
    const validNodes = graph.nodes.filter(n => !displayTypeSet.has(n.type));

    // 确保全局计数器高于图中已有节点 ID 的数字后缀
    for (const n of validNodes) {
      const m = n.id.match(/-(\d+)$/);
      if (m) {
        const num = parseInt(m[1], 10);
        if (num >= _globalNodeCounter) _globalNodeCounter = num + 1;
      }
    }

    const nodes: Node[] = validNodes.map((n) => {
      const data: BusinessNodeData = {
        label: n.type,
        nodeType: n.type,
        params: n.params as unknown as Record<string, unknown>,
        schema: schemaByType[n.type],
        collapsed: (n.ui as Record<string, unknown> | undefined)?.["collapsed"] as boolean
          ?? n.collapsed ?? false,
        status: "idle",
        onParamChange: stableParamChange,
        onCollapsedChange: stableCollapsedChange,
      };
      return {
        id: n.id,
        type: "business",
        position: { x: n.x, y: n.y },
        data,
        selected: n.id === selectedNodeId,
      };
    });

    const edges: Edge[] = graph.edges
      .filter((e) => !displayNodeIds.has(e.src_node) && !displayNodeIds.has(e.dst_node))
      .map((e) => ({
        id: e.id,
        source: e.src_node,
        target: e.dst_node,
        sourceHandle: e.src_port,
        targetHandle: e.dst_port,
        type: edgeType,
        animated: true,
        style: { stroke: "var(--acc)", strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--acc)" },
      }));

    // 在构建节点时合并已有的 nodeStatuses（页面重进恢复上次运行结果）
    const currentStatuses = nodeStatusesRef.current;
    const hasStatuses = Object.keys(currentStatuses).length > 0;
    const finalNodes = hasStatuses
      ? nodes.map((n) => _applyNodeStatus(n, currentStatuses, stableParamChange, stableCollapsedChange))
      : nodes;

    if (hasStatuses) {
      console.log("[PipelineCanvas][graph-build] Applying existing nodeStatuses on graph build:", Object.keys(currentStatuses));
      appliedStatusesKeyRef.current = key;
    }

    setRfNodes(finalNodes);
    setRfEdges(edges);

    // 恢复初始 viewport（仅首次加载时）
    if (initialViewport && !viewportAppliedRef.current) {
      viewportAppliedRef.current = true;
      setTimeout(() => {
        reactFlowInstance.setViewport({
          x: initialViewport.x ?? 0,
          y: initialViewport.y ?? 0,
          zoom: initialViewport.zoom ?? 1,
        });
      }, 50);
    }
    // stableParamChange 是稳定的（useCallback 只有 setRfNodes 依赖），可以安全地放在 deps
  }, [graph, selectedNodeId, setRfNodes, setRfEdges, stableParamChange, stableCollapsedChange, initialViewport, reactFlowInstance, schemaByType]);

  // 重置 viewport applied 标记（当 graph id 变化时）
  useEffect(() => {
    viewportAppliedRef.current = false;
  }, [graph?.id]);

  // ===== Effect: selectedNodeId 变化 → 高亮更新 =====
  useEffect(() => {
    setRfNodes((nds) =>
      nds.map((n) => ({ ...n, selected: n.id === selectedNodeId }))
    );
  }, [selectedNodeId, setRfNodes]);

  // ===== Effect: nodeStatuses 变化 → 配置节点状态灯 + 展示节点结果映射 =====
  useEffect(() => {
    const entries = Object.entries(nodeStatuses);
    if (entries.length > 0) {
      console.log("[PipelineCanvas][nodeStatuses-effect] Applying nodeStatuses to display nodes. Keys:", Object.keys(nodeStatuses), "Count:", Object.values(nodeStatuses).filter(s => s.thumbnail || s.url).length, "with thumbnail/url");
    }
    setRfNodes((nds) => {
      const updated = nds.map((n) => _applyNodeStatus(n, nodeStatuses, stableParamChange, stableCollapsedChange));
      return updated;
    });
  }, [nodeStatuses, setRfNodes, stableParamChange, stableCollapsedChange]);

  /**
   * 将一个节点合并 nodeStatuses 数据（直接注入到业务节点）
   */
  function _applyNodeStatus(
    n: Node,
    statuses: Record<string, { status: string; thumbnail?: string | null; error?: string | null; assetId?: string | null; url?: string | null }>,
    spc: (nodeId: string, params: Record<string, unknown>) => void,
    scc: (nodeId: string, collapsed: boolean) => void,
  ): Node {
    const st = statuses[n.id];
    if (!st) return n;
    const data = n.data as unknown as BusinessNodeData;
    return {
      ...n,
      data: {
        ...data,
        status: (st.status as BusinessNodeData["status"]) ?? "idle",
        thumbnail: st.thumbnail ?? null,
        assetId: st.assetId ?? null,
        url: st.url ?? null,
        error: st.error ?? null,
        onParamChange: spc,
        onCollapsedChange: scc,
      },
    };
  }

  const buildGraph = useCallback(
    (nodes: Node[], edges: Edge[]): PipelineGraphModel => {
      const vp = viewportRef.current;
      return {
        schema_version: graphRef.current?.schema_version ?? 1,
        id: graphRef.current?.id ?? "",
        name: graphRef.current?.name ?? "",
        description: graphRef.current?.description ?? "",
        spec_id: graphRef.current?.spec_id ?? null,
        viewport: { x: vp.x, y: vp.y, zoom: vp.zoom },
        tags: graphRef.current?.tags ?? [],
        nodes: nodes.map(
          (n): PipelineNodeModel => {
            const d = n.data as unknown as BusinessNodeData;
            return {
              id: n.id,
              type: d.nodeType,
              x: n.position.x,
              y: n.position.y,
              width: n.measured?.width ?? null,
              height: n.measured?.height ?? null,
              collapsed: (d.ui as Record<string, unknown> | undefined)?.["collapsed"] as boolean ?? d.collapsed ?? false,
              params: d.params as PipelineNodeParams,
              ui: (d.ui as Record<string, unknown>) ?? {},
            };
          }
        ),
        edges: edges.map(
          (e): GraphEdgeModel => ({
            id: e.id,
            src_node: e.source,
            src_port: (e.sourceHandle as string) ?? "image",
            dst_node: e.target,
            dst_port: (e.targetHandle as string) ?? "image",
          })
        ),
      };
    },
    []
  );

  // 节点移动 / 删除：同步到 graph
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setRfNodes((nds) => {
        let updated = applyNodeChanges(changes, nds) as Node[];

        const shouldEmit = changes.some((c) =>
          c.type === "position" || c.type === "remove"
        );
        if (shouldEmit) {
          setTimeout(() => {
            onChange(buildGraph(updated, rfEdgesRef.current));
          }, 0);
        }
        return updated;
      });
    },
    [setRfNodes, onChange, buildGraph]
  );

  // 边删除 / 重连：同步到 graph
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setRfEdges((eds) => {
        const updated = applyEdgeChanges(changes, eds) as Edge[];
        const shouldEmit = changes.some((c) => c.type === "remove");
        if (shouldEmit) {
          setTimeout(() => {
            onChange(buildGraph(rfNodesRef.current, updated));
          }, 0);
        }
        return updated;
      });
    },
    [setRfEdges, onChange, buildGraph]
  );

  const createNode = useCallback(
    (nodeType: string, position: { x: number; y: number }): { nodes: Node[]; edges: Edge[] } => {
      const schema = schemaByType[nodeType];
      const id = `${nodeType.toLowerCase()}-${++_globalNodeCounter}`;
      const defaults = { ...(NODE_DEFAULTS[nodeType] ?? {}), ...defaultsFromSchema(schema) };

      const businessNode: Node = {
        id,
        type: "business",
        position,
        data: {
          label: schema?.label ?? nodeType,
          nodeType,
          schema,
          params: defaults as Record<string, unknown>,
          collapsed: false,
          status: "idle",
          onParamChange: stableParamChange,
          onCollapsedChange: stableCollapsedChange,
        } satisfies BusinessNodeData,
      };

      return { nodes: [businessNode], edges: [] };
    },
    [schemaByType, stableParamChange, stableCollapsedChange]
  );

  const getPortType = useCallback(
    (nodeId: string, portId: string | null | undefined, direction: "source" | "target") => {
      const node = rfNodesRef.current.find((n) => n.id === nodeId);
      const nodeType = (node?.data as unknown as BusinessNodeData | undefined)?.nodeType;
      const schema = nodeType ? schemaByType[nodeType] : undefined;
      const ports = direction === "source" ? schema?.outputs : schema?.inputs;
      return ports?.[portId ?? ""];
    },
    [schemaByType]
  );

  // 连线
  const onConnect: OnConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target) return;
      const sourceType = getPortType(conn.source, conn.sourceHandle, "source");
      const targetType = getPortType(conn.target, conn.targetHandle, "target");
      const compatible =
        sourceType === targetType ||
        sourceType === "ANY" ||
        targetType === "ANY" ||
        (sourceType === "IMAGE_BATCH" && targetType === "IMAGE") ||
        (sourceType === "IMAGE" && targetType === "IMAGE_BATCH");
      if (sourceType && targetType && !compatible) {
        console.warn(`端口类型不兼容: ${sourceType} -> ${targetType}`);
        return;
      }
      setRfEdges((eds) => {
        const updated = addEdge(
          {
            ...conn,
            type: edgeType,
            animated: true,
            style: { stroke: "var(--acc)", strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "var(--acc)" },
          },
          eds
        );
        setTimeout(() => {
          onChange(buildGraph(rfNodesRef.current, updated));
        }, 0);
        return updated;
      });
    },
    [setRfEdges, onChange, buildGraph, getPortType]
  );

  // 拖入节点
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const nodeType = e.dataTransfer.getData("application/node-type");
      if (!nodeType || !reactFlowWrapper.current) return;

      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = {
        x: e.clientX - bounds.left - 90,
        y: e.clientY - bounds.top - 30,
      };

      const { nodes: newNodes, edges: newEdges } = createNode(nodeType, position);

      setRfNodes((nds) => {
        setRfEdges((eds) => {
          const updatedNodes = [...nds, ...newNodes];
          const updatedEdges = [...eds, ...newEdges];
          setTimeout(() => {
            onChange(buildGraph(updatedNodes, updatedEdges));
          }, 0);
          return updatedEdges;
        });
        return [...nds, ...newNodes];
      });
    },
    [setRfNodes, setRfEdges, onChange, buildGraph, createNode]
  );

  const onNodeClick = useCallback(
    (_e: React.MouseEvent, node: Node) => {
      onSelectNode(node.id);
    },
    [onSelectNode]
  );

  const onPaneClick = useCallback(() => {
    onSelectNode(null);
    setContextMenu((m) => ({ ...m, open: false }));
    setSearchState((s) => ({ ...s, open: false }));
  }, [onSelectNode]);

  const openSearch = useCallback((clientX: number, clientY: number) => {
    setSearchState({ open: true, x: clientX, y: clientY, query: "" });
  }, []);

  const addNodeAt = useCallback((nodeType: string, clientX: number, clientY: number) => {
    if (!reactFlowWrapper.current) return;
    const position = reactFlowInstance.screenToFlowPosition({ x: clientX, y: clientY });
    const { nodes: newNodes, edges: newEdges } = createNode(nodeType, position);
    setRfNodes((nds) => {
      setRfEdges((eds) => {
        const updatedNodes = [...nds, ...newNodes];
        const updatedEdges = [...eds, ...newEdges];
        setTimeout(() => onChange(buildGraph(updatedNodes, updatedEdges)), 0);
        return updatedEdges;
      });
      return [...nds, ...newNodes];
    });
    setSearchState((s) => ({ ...s, open: false }));
    setContextMenu((m) => ({ ...m, open: false }));
  }, [reactFlowInstance, createNode, setRfNodes, setRfEdges, onChange, buildGraph]);

  const copySelected = useCallback((nodeId?: string | null) => {
    if (nodeId) {
      // 右键节点菜单 → 只复制该节点
      clipboardRef.current = rfNodesRef.current.filter((n) => n.id === nodeId);
    } else {
      // 画布菜单 / 快捷键 → 复制所有 React Flow 选中的节点
      const selected = rfNodesRef.current.filter((n) => n.selected);
      if (selected.length > 0) {
        clipboardRef.current = selected;
      } else if (selectedNodeIdRef.current) {
        // React Flow 选中状态尚未同步（打开已保存图后首次点击节点时），回退到 selectedNodeIdRef
        clipboardRef.current = rfNodesRef.current.filter((n) => n.id === selectedNodeIdRef.current);
      } else {
        clipboardRef.current = [];
      }
    }
  }, []);

  const pasteClipboard = useCallback(() => {
    if (clipboardRef.current.length === 0) return;
    const idMap = new Map<string, string>();
    const pasted: Node[] = clipboardRef.current.map((n) => {
      const oldId = n.id;
      const d = n.data as unknown as BusinessNodeData;
      const newId = `${d.nodeType.toLowerCase()}-${++_globalNodeCounter}`;
      idMap.set(oldId, newId);
      return {
        ...n,
        id: newId,
        position: { x: n.position.x + 40, y: n.position.y + 40 },
        selected: false,
        data: { ...n.data },
      };
    });

    const clipboardIds = new Set(clipboardRef.current.map((n) => n.id));
    const pastedEdges: Edge[] = [];
    for (const e of rfEdgesRef.current) {
      if (clipboardIds.has(e.source) && clipboardIds.has(e.target)) {
        const newSource = idMap.get(e.source);
        const newTarget = idMap.get(e.target);
        if (newSource && newTarget) {
          pastedEdges.push({
            ...e,
            id: `e-${newSource}-${newTarget}-${++_globalNodeCounter}`,
            source: newSource,
            target: newTarget,
          });
        }
      }
    }

    setRfNodes((nds) => {
      setRfEdges((eds) => {
        const updatedNodes = [...nds, ...pasted];
        const updatedEdges = [...eds, ...pastedEdges];
        setTimeout(() => onChange(buildGraph(updatedNodes, updatedEdges)), 0);
        return updatedEdges;
      });
      return [...nds, ...pasted];
    });
  }, [setRfNodes, setRfEdges, onChange, buildGraph]);

  const deleteSelected = useCallback((nodeId?: string | null) => {
    setRfNodes((nds) => {
      let selectedIds: Set<string>;
      if (nodeId) {
        selectedIds = new Set(nds.filter((n) => n.id === nodeId).map((n) => n.id));
      } else {
        const reactFlowSelected = nds.filter((n) => n.selected);
        if (reactFlowSelected.length > 0) {
          selectedIds = new Set(reactFlowSelected.map((n) => n.id));
        } else if (selectedNodeIdRef.current) {
          selectedIds = new Set(nds.filter((n) => n.id === selectedNodeIdRef.current).map((n) => n.id));
        } else {
          selectedIds = new Set();
        }
      }
      if (selectedIds.size === 0) return nds;

      const updatedNodes = nds.filter((n) => !selectedIds.has(n.id));
      const updatedEdges = rfEdgesRef.current.filter(
        (e) => !selectedIds.has(e.source) && !selectedIds.has(e.target)
      );
      setRfEdges(updatedEdges);
      setTimeout(() => onChange(buildGraph(updatedNodes, updatedEdges)), 0);
      onSelectNode(null);
      return updatedNodes;
    });
  }, [setRfNodes, setRfEdges, onChange, buildGraph, onSelectNode]);

  const onFlowDoubleClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest(".react-flow__node") || target.closest(".react-flow__edge")) return;
    openSearch(e.clientX, e.clientY);
  }, [openSearch]);

  const onPaneContextMenu = useCallback((e: MouseEvent | React.MouseEvent<Element, MouseEvent>) => {
    e.preventDefault();
    setContextMenu({ open: true, x: e.clientX, y: e.clientY, nodeId: null });
  }, []);

  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault();
    onSelectNode(node.id);
    setContextMenu({ open: true, x: e.clientX, y: e.clientY, nodeId: node.id, edgeId: null });
  }, [onSelectNode]);

  const onEdgeContextMenu = useCallback((e: React.MouseEvent, edge: Edge) => {
    e.preventDefault();
    setContextMenu({ open: true, x: e.clientX, y: e.clientY, nodeId: null, edgeId: edge.id });
  }, []);

  const deleteEdge = useCallback((edgeId: string) => {
    setRfEdges((eds) => {
      const updated = eds.filter((e) => e.id !== edgeId);
      setTimeout(() => {
        onChange(buildGraph(rfNodesRef.current, updated));
      }, 0);
      return updated;
    });
  }, [setRfEdges, onChange, buildGraph]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (e.key === "Tab") {
        e.preventDefault();
        const rect = reactFlowWrapper.current?.getBoundingClientRect();
        openSearch((rect?.left ?? 0) + (rect?.width ?? 800) / 2, (rect?.top ?? 0) + (rect?.height ?? 600) / 2);
      } else if (mod && e.key.toLowerCase() === "c") {
        e.preventDefault();
        copySelected();
      } else if (mod && e.key.toLowerCase() === "v") {
        e.preventDefault();
        pasteClipboard();
      } else if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        onSaveShortcut?.();
      } else if (mod && e.key === "Enter") {
        e.preventDefault();
        onRunShortcut?.();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openSearch, copySelected, pasteClipboard, onSaveShortcut, onRunShortcut]);

  // viewport 变化跟踪
  const onMoveEnd = useCallback(
    (_e: any, vp: { x: number; y: number; zoom: number }) => {
      viewportRef.current = vp;
    },
    []
  );

  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      if (deleted.some((n) => n.id === selectedNodeId)) {
        onSelectNode(null);
      }
    },
    [selectedNodeId, onSelectNode]
  );

  const allSearchSchemas = useMemo(() => {
    return nodeSchemas;
  }, [nodeSchemas]);

  const visibleSearchNodes = allSearchSchemas.filter((schema) => {
    const q = searchState.query.trim().toLowerCase();
    if (!q) return true;
    return [schema.type, schema.label, schema.description].filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
  });

  const styledEdges = useMemo(() => {
    const failedNodeIds = new Set(Object.entries(nodeStatuses).filter(([, st]) => st.status === "failed").map(([id]) => id));
    const runningNodeIds = new Set(Object.entries(nodeStatuses).filter(([, st]) => st.status === "running").map(([id]) => id));
    const failedEdgeIds = new Set<string>();
    failedNodeIds.forEach((id) => {
      const node = rfNodes.find((n) => n.id === id);
      if (!node) return;
      getIncomers(node, rfNodes, rfEdges).forEach((src) => {
        rfEdges.filter((e) => e.source === src.id && e.target === id).forEach((e) => failedEdgeIds.add(e.id));
      });
    });
    return rfEdges.map((e) => {
      const failed = failedEdgeIds.has(e.id) || failedNodeIds.has(e.target);
      const running = runningNodeIds.has(e.source) || runningNodeIds.has(e.target);
      return {
        ...e,
        animated: failed ? false : running || e.animated,
        style: {
          ...(e.style ?? {}),
          stroke: failed ? "#ef4444" : running ? "#3b82f6" : "var(--acc)",
          strokeWidth: failed || running ? 3 : 2,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: failed ? "#ef4444" : running ? "#3b82f6" : "var(--acc)" },
      };
    });
  }, [rfEdges, rfNodes, nodeStatuses]);

  return (
    <div ref={reactFlowWrapper} className="w-full h-full">
      <ReactFlow
        nodes={rfNodes}
        edges={styledEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        onEdgeContextMenu={onEdgeContextMenu}
        onPaneClick={onPaneClick}
        onDoubleClick={onFlowDoubleClick}
        onPaneContextMenu={onPaneContextMenu}
        onMoveEnd={onMoveEnd}
        onNodesDelete={onNodesDelete}
        onDragOver={onDragOver}
        onDrop={onDrop}
        nodeTypes={NODE_TYPES}
        fitView
        snapToGrid
        snapGrid={[16, 16]}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: edgeType,
          animated: true,
          style: { stroke: "var(--acc)", strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "var(--acc)" },
        }}
        deleteKeyCode={["Backspace", "Delete"]}
        style={{ background: "var(--bg-0)" }}
      >
        {showBackground && <Background gap={20} size={1} color="#1f2433" />}
        {showControls && (
          <Controls
            className="!bg-[#0c0e15] !border-[#1f2433] !rounded-lg"
            style={{
              "--xy-controls-button-background-color": "#11141d",
              "--xy-controls-button-background-color-hover": "#161a25",
              "--xy-controls-button-color": "#6c7488",
              "--xy-controls-button-color-hover": "#aab2c5",
            } as React.CSSProperties}
          />
        )}
        {showMiniMap && (
          <MiniMap
            style={{ background: "#0c0e15", border: "1px solid #1f2433", borderRadius: 8 }}
            maskColor="rgba(0,0,0,0.5)"
            nodeColor={(n: Node) => {
              const d = n.data as unknown as BusinessNodeData | undefined;
              const type = d?.nodeType;
              return type ? (schemaByType[type]?.color ?? "var(--acc)") : "var(--acc)";
            }}
          />
        )}
      </ReactFlow>

      {/* 连线样式切换 */}
      <div
        className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 rounded-lg border px-1.5 py-1"
        style={{ background: "#0c0e15", borderColor: "#252a3d" }}
      >
        <span className="text-[9px] mr-1 uppercase tracking-wider" style={{ color: "var(--txt-3)" }}>
          连线
        </span>
        {(["straight", "smoothstep", "bezier"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className="px-1.5 py-0.5 rounded text-[10px] transition-colors"
            style={{
              background: edgeType === t ? "var(--acc)" : "transparent",
              color: edgeType === t ? "#fff" : "var(--txt-3)",
            }}
            onClick={() => setEdgeType(t)}
            title={t === "straight" ? "直线" : t === "smoothstep" ? "直角折线" : "贝塞尔曲线"}
          >
            {t === "straight" ? "━" : t === "smoothstep" ? "┗" : "⌇"}
          </button>
        ))}
      </div>

      {searchState.open && (
        <div
          className="fixed z-50 w-64 rounded-xl border shadow-2xl overflow-hidden"
          style={{ left: searchState.x, top: searchState.y, background: "#0c0e15", borderColor: "#252a3d" }}
        >
          <input
            autoFocus
            className="w-full h-9 px-3 text-[12px] bg-transparent outline-none border-b"
            style={{ color: "var(--txt-0)", borderColor: "#252a3d" }}
            placeholder={t("graph.searchNode", "搜索节点...")}
            value={searchState.query}
            onChange={(e) => setSearchState((s) => ({ ...s, query: e.target.value }))}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSearchState((s) => ({ ...s, open: false }));
              if (e.key === "Enter" && visibleSearchNodes[0]) addNodeAt(visibleSearchNodes[0].type, searchState.x, searchState.y);
            }}
          />
          <div className="max-h-72 overflow-y-auto py-1">
            {visibleSearchNodes.map((schema) => (
              <button
                key={schema.type}
                type="button"
                className="w-full px-3 py-2 flex items-center gap-2 text-left hover:bg-white/5"
                onClick={() => addNodeAt(schema.type, searchState.x, searchState.y)}
              >
                <span style={{ color: schema.color ?? "#6366f1" }}>{schema.icon ?? "📦"}</span>
                <span className="min-w-0">
                  <span className="block text-[12px] font-medium" style={{ color: "var(--txt-0)" }}>{schema.label ?? schema.type}</span>
                  <span className="block text-[10px] truncate" style={{ color: "var(--txt-3)" }}>{schema.description}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {contextMenu.open && (
        <div
          className="fixed z-[60] min-w-36 rounded-lg border py-1 shadow-2xl"
          style={{ left: contextMenu.x, top: contextMenu.y, background: "#0c0e15", borderColor: "#252a3d" }}
        >
          {contextMenu.edgeId && (
            <>
              <MenuItem onClick={() => { deleteEdge(contextMenu.edgeId!); setContextMenu((m) => ({ ...m, open: false })); }}>
                {t("graph.deleteEdge", "删除连线")}
              </MenuItem>
              <div style={{ height: 1, background: "#252a3d", margin: "4px 0" }} />
            </>
          )}
          {contextMenu.nodeId && onRerunNode && (
            <>
              <MenuItem onClick={() => { onRerunNode(contextMenu.nodeId!); setContextMenu((m) => ({ ...m, open: false })); }}>
                {t("graph.rerunNodeDownstream", "重新运行此节点及下游")}
              </MenuItem>
              <MenuItem onClick={() => { onRerunNode(contextMenu.nodeId!, "node_only"); setContextMenu((m) => ({ ...m, open: false })); }}>
                {t("graph.rerunNodeOnly", "仅运行此节点")}
              </MenuItem>
              <MenuItem onClick={() => { onRerunNode(contextMenu.nodeId!, "downstream_only"); setContextMenu((m) => ({ ...m, open: false })); }}>
                {t("graph.rerunDownstreamOnly", "仅运行下游节点")}
              </MenuItem>
              <div style={{ height: 1, background: "#252a3d", margin: "4px 0" }} />
            </>
          )}
          <MenuItem onClick={() => { openSearch(contextMenu.x, contextMenu.y); setContextMenu((m) => ({ ...m, open: false })); }}>
            {t("graph.addNode", "添加节点")}
          </MenuItem>
          <MenuItem onClick={() => { copySelected(contextMenu.nodeId); setContextMenu((m) => ({ ...m, open: false })); }}>
            {t("graph.copy", "复制")}
          </MenuItem>
          <MenuItem onClick={() => { pasteClipboard(); setContextMenu((m) => ({ ...m, open: false })); }}>
            {t("graph.paste", "粘贴")}
          </MenuItem>
          <MenuItem onClick={() => { deleteSelected(contextMenu.nodeId); setContextMenu((m) => ({ ...m, open: false })); }}>
            {t("graph.deleteSelected", "删除选中")}
          </MenuItem>
        </div>
      )}
    </div>
  );
}

function MenuItem({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      className="block w-full px-3 py-1.5 text-left text-[12px] hover:bg-white/5"
      style={{ color: "var(--txt-1)" }}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

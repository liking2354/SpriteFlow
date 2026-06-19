import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FiChevronDown, FiChevronRight, FiInfo } from "react-icons/fi";
import type { CanvasNodeStatus } from "./useGraphRun";

export interface LogEntry {
  id: number;
  timestamp: Date;
  nodeId: string;
  nodeLabel: string;
  event: string;
  status: string;
  message?: string;
  inputs?: Record<string, unknown> | null;
}

interface ExecutionLogProps {
  /** 当前节点状态映射（用于构建日志条目） */
  nodeStatuses: Record<string, CanvasNodeStatus>;
  /** 节点类型到标签的映射 */
  nodeLabels: Record<string, string>;
  /** 是否正在运行 */
  isRunning: boolean;
  /** 默认是否折叠（底部控制台模式下默认折叠） */
  defaultCollapsed?: boolean;
  /** 清除日志时回调 */
  onClear?: () => void;
}

let _logCounter = 0;

const STATUS_COLORS: Record<string, string> = {
  pending: "#f59e0b",
  queued: "#a78bfa",
  running: "#3b82f6",
  completed: "#10b981",
  failed: "#ef4444",
};

export function ExecutionLog({ nodeStatuses, nodeLabels, isRunning, defaultCollapsed = false, onClear }: ExecutionLogProps) {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [expandedEntries, setExpandedEntries] = useState<Set<number>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);
  const prevRef = useRef<Record<string, string>>({}); // nodeId → status

  // 监听 defaultCollapsed 变化（父组件切换时同步）
  useEffect(() => {
    setCollapsed(defaultCollapsed);
  }, [defaultCollapsed]);

  // 检测节点状态变化 → 生成日志
  useEffect(() => {
    const newLogs: LogEntry[] = [];
    for (const [nid, st] of Object.entries(nodeStatuses)) {
      const prevStatus = prevRef.current[nid];
      if (prevStatus !== st.status) {
        prevRef.current[nid] = st.status;
        newLogs.push({
          id: ++_logCounter,
          timestamp: new Date(),
          nodeId: nid,
          nodeLabel: nodeLabels[nid] ?? nid,
          event: st.status,
          status: st.status,
          message: st.error ?? undefined,
          inputs: st.status === "completed" ? (st.inputs ?? null) : null,
        });
      }
    }
    if (newLogs.length > 0) {
      setLogs((prev) => [...prev, ...newLogs].slice(-100)); // 最多保留 100 条
    }
  }, [nodeStatuses, nodeLabels]);

  // 自动滚到底部
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  // 新运行开始时清空旧日志
  useEffect(() => {
    if (isRunning) {
      prevRef.current = {};
      setLogs([]);
      setExpandedEntries(new Set());
    }
  }, [isRunning]);

  return (
    <div className="flex flex-col">
      {/* 标题栏 */}
      <button
        type="button"
        className="px-3 py-2 flex items-center justify-between hover:bg-white/5 transition-colors"
        onClick={() => setCollapsed((v) => !v)}
      >
        <div className="flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: isRunning ? "#3b82f6" : logs.length > 0 ? "#10b981" : "var(--txt-3)",
            }}
          />
          <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--txt-2)" }}>
            {t("graph.executionLog", "执行日志")}
          </span>
          {logs.length > 0 && (
            <span className="text-[9px] px-1.5 py-px rounded-full" style={{ background: "#ffffff10", color: "var(--txt-3)" }}>
              {logs.length}
            </span>
          )}
          {isRunning && (
            <span className="animate-spin inline-block w-3 h-3 border-2 border-white/30 border-t-white/80 rounded-full" />
          )}
          {!isRunning && logs.length > 0 && (
            <button
              type="button"
              className="ml-auto text-[9px] px-1.5 py-0.5 rounded hover:bg-white/10 transition-colors"
              style={{ color: "var(--txt-3)" }}
              onClick={(e) => {
                e.stopPropagation();
                prevRef.current = {};
                setLogs([]);
                setExpandedEntries(new Set());
                onClear?.();
              }}
            >
              清除
            </button>
          )}
        </div>
        <span className="text-[12px]" style={{ color: "var(--txt-3)" }}>
          {collapsed ? <FiChevronRight size={14} /> : <FiChevronDown size={14} />}
        </span>
      </button>

      {/* 日志列表 */}
      {!collapsed && (
        <div
          ref={containerRef}
          className="overflow-y-auto px-2"
          style={{ maxHeight: 200 }}
        >
          {logs.length === 0 ? (
            <div className="py-4 text-center text-[10px]" style={{ color: "var(--txt-3)" }}>
              {isRunning
                ? t("graph.waitingForEvents", "等待执行...")
                : t("graph.noLogs", "暂无日志")}
            </div>
          ) : (
            <div className="flex flex-col gap-px py-1">
              {logs.map((log) => {
                const isExpanded = expandedEntries.has(log.id);
                const hasInputs = log.status === "completed" && log.inputs && Object.keys(log.inputs).length > 0;
                return (
                <div key={log.id}>
                  <div
                    className={`px-2 py-1 rounded text-[10px] flex items-start gap-1.5 leading-snug ${hasInputs ? "cursor-pointer hover:bg-white/10" : ""}`}
                    style={{ background: log.id === logs[logs.length - 1]?.id ? "#ffffff05" : "transparent" }}
                    onClick={() => {
                      if (hasInputs) {
                        setExpandedEntries((prev) => {
                          const next = new Set(prev);
                          if (isExpanded) next.delete(log.id);
                          else next.add(log.id);
                          return next;
                        });
                      }
                    }}
                  >
                    <span className="shrink-0 mt-px" title={log.event}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: STATUS_COLORS[log.event] ?? "var(--txt-3)", display: "inline-block" }} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <span className="font-medium" style={{ color: "var(--txt-1)" }}>
                        {log.nodeLabel}
                      </span>
                      <span className="mx-1" style={{ color: "var(--txt-3)" }}>·</span>
                      <span style={{ color: STATUS_COLORS[log.event] ?? "var(--txt-2)" }}>
                        {t(`graph.status.${log.event}`, log.event)}
                      </span>
                      {hasInputs && (
                        <span className="ml-1" style={{ color: "var(--txt-3)", fontSize: "9px" }}>
                          [{isExpanded ? "收起" : "查看提示词"}]
                        </span>
                      )}
                      {log.message && (
                        <div className="mt-0.5 text-[9px] break-all" style={{ color: "#ef4444" }}>
                          {log.message}
                        </div>
                      )}
                    </div>
                    <span className="shrink-0 text-[9px]" style={{ color: "var(--txt-3)" }}>
                      {log.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                  {isExpanded && log.inputs && (
                    <div
                      className="mx-3 mb-1 px-2 py-1.5 rounded text-[9px] leading-relaxed font-mono whitespace-pre-wrap break-all"
                      style={{ background: "#00000020", color: "var(--txt-2)", maxHeight: 200, overflowY: "auto" }}
                    >
                      <PromptView inputs={log.inputs} />
                    </div>
                  )}
                </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** 渲染 inputs 快照为可读格式 */
function PromptView({ inputs }: { inputs: Record<string, unknown> }) {
  // 动画精灵节点：展示每个动作的提示词（prompts 数组）
  const prompts = inputs.prompts as Array<{ name: string; prompt: string }> | undefined;
  if (prompts && Array.isArray(prompts)) {
    return (
      <div className="flex flex-col gap-1">
        {prompts.map((v, i) => (
          <div key={i}>
            <span style={{ color: "#10b981", fontWeight: 600 }}>{v.name}:</span>
            <span style={{ color: "var(--txt-1)" }}> {v.prompt}</span>
          </div>
        ))}
        {(inputs.template_ids || inputs.slot_values) && (
          <div className="mt-0.5 pt-0.5" style={{ borderTop: "1px solid #ffffff10" }}>
            {inputs.template_ids && (
              <div style={{ color: "var(--txt-3)" }}>
                template_ids: {JSON.stringify(inputs.template_ids)}
              </div>
            )}
            {inputs.slot_values && (
              <div style={{ color: "var(--txt-3)" }}>
                slot_values: {JSON.stringify(inputs.slot_values)}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // 方向变体节点：展示每个变体的名称和提示词
  const variants = inputs.variants as Array<{ name: string; prompt: string }> | undefined;
  if (variants && Array.isArray(variants)) {
    return (
      <div className="flex flex-col gap-1">
        {variants.map((v, i) => (
          <div key={i}>
            <span style={{ color: "#a78bfa", fontWeight: 600 }}>{v.name}:</span>
            <span style={{ color: "var(--txt-1)" }}> {v.prompt}</span>
          </div>
        ))}
        {(inputs.template_ids || inputs.slot_values) && (
          <div className="mt-0.5 pt-0.5" style={{ borderTop: "1px solid #ffffff10" }}>
            {inputs.template_ids && (
              <div style={{ color: "var(--txt-3)" }}>
                template_ids: {JSON.stringify(inputs.template_ids)}
              </div>
            )}
            {inputs.slot_values && (
              <div style={{ color: "var(--txt-3)" }}>
                slot_values: {JSON.stringify(inputs.slot_values)}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // 普通节点：展示 prompt
  const prompt = inputs.prompt as string | undefined;
  const params = inputs.params as Record<string, unknown> | undefined;
  const templateIds = inputs.template_ids;

  return (
    <div className="flex flex-col gap-0.5">
      {prompt && (
        <div>
          <span style={{ color: "#60a5fa", fontWeight: 600 }}>prompt: </span>
          <span style={{ color: "var(--txt-1)" }}>{prompt}</span>
        </div>
      )}
      {templateIds && (
        <div style={{ color: "var(--txt-3)" }}>
          template_ids: {JSON.stringify(templateIds)}
        </div>
      )}
      {params && Object.keys(params).length > 0 && (
        <div style={{ color: "var(--txt-3)" }}>
          params: {JSON.stringify(params)}
        </div>
      )}
    </div>
  );
}

import { useTranslation } from "react-i18next";
import type { GraphRunSummary } from "@/api/types";

interface RunSummaryProps {
  summary: GraphRunSummary | null;
  duration: number;
  onClose?: () => void;
  onNodeClick?: (nodeId: string) => void;
}

export function RunSummary({ summary, duration, onClose, onNodeClick }: RunSummaryProps) {
  const { t } = useTranslation();

  if (!summary) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-40 w-80 rounded-xl border shadow-2xl overflow-hidden"
      style={{ background: "#0c0e15", borderColor: "#252a3d" }}
    >
      {/* 头部 */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: "#252a3d" }}
      >
        <span
          className="text-[12px] font-semibold"
          style={{ color: "var(--txt-0)" }}
        >
          {t("graph.runSummary", "运行摘要")}
        </span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-[18px] leading-none hover:opacity-70"
            style={{ color: "var(--txt-3)" }}
          >
            ×
          </button>
        )}
      </div>

      {/* 统计 */}
      <div className="px-4 py-3 flex flex-col gap-2">
        <div className="flex items-center justify-between text-[11px]">
          <span style={{ color: "var(--txt-3)" }}>{t("graph.duration", "耗时")}</span>
          <span style={{ color: "var(--txt-1)", fontWeight: 600 }}>{duration}s</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span style={{ color: "var(--txt-3)" }}>{t("graph.successNodes", "成功节点")}</span>
          <span style={{ color: "#10b981", fontWeight: 600 }}>{summary.successCount}</span>
        </div>
        {summary.failedCount > 0 && (
          <div className="flex items-center justify-between text-[11px]">
            <span style={{ color: "var(--txt-3)" }}>{t("graph.failedNodes", "失败节点")}</span>
            <span style={{ color: "#ef4444", fontWeight: 600 }}>{summary.failedCount}</span>
          </div>
        )}
        <div className="flex items-center justify-between text-[11px]">
          <span style={{ color: "var(--txt-3)" }}>{t("graph.cacheHits", "缓存命中")}</span>
          <span style={{ color: "#a78bfa", fontWeight: 600 }}>{summary.cacheHits}</span>
        </div>
      </div>

      {/* 失败节点详情 */}
      {summary.failedNodes.length > 0 && (
        <div
          className="px-4 py-2 border-t"
          style={{ borderColor: "#252a3d" }}
        >
          <div className="text-[10px] font-semibold mb-2" style={{ color: "#ef4444" }}>
            {t("graph.failedNodesDetail", "失败节点详情")}
          </div>
          {summary.failedNodes.map((fn) => (
            <div
              key={fn.nodeId}
              className="text-[10px] mb-1 px-2 py-1 rounded"
              style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444" }}
            >
              <span
                className="cursor-pointer underline"
                onClick={() => onNodeClick?.(fn.nodeId)}
              >
                {fn.nodeId}
              </span>
              {fn.error && <span>: {fn.error.slice(0, 100)}</span>}
            </div>
          ))}
        </div>
      )}

      {/* 输出素材列表 */}
      {summary.assets.length > 0 && (
        <div
          className="px-4 py-2 border-t"
          style={{ borderColor: "#252a3d" }}
        >
          <div className="text-[10px] font-semibold mb-2" style={{ color: "var(--txt-2)" }}>
            {t("graph.outputAssets", "输出素材")} ({summary.assets.length})
          </div>
          <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
            {summary.assets.map((a) => (
              <div
                key={`${a.nodeId}-${a.assetId}`}
                className="text-[10px] flex items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-white/5"
                onClick={() => onNodeClick?.(a.nodeId)}
              >
                <span style={{ color: "#10b981" }}>●</span>
                <span style={{ color: "var(--txt-3)" }}>{a.nodeId}</span>
                <span className="truncate" style={{ color: "var(--txt-1)" }}>
                  {a.assetId}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

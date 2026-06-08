import { memo, useMemo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface DisplayNodeData extends Record<string, unknown> {
  label: string;
  nodeType: "ImageViewer" | "GalleryViewer";
  /** 上游配置节点 ID，用于从 SSE 结果路由到展示节点 */
  configNodeId: string;
  thumbnail?: string | null;
  assetId?: string | null;
  url?: string | null;
  status?: "idle" | "pending" | "queued" | "running" | "completed" | "failed";
  error?: string | null;
  onThumbnailClick?: (nodeId: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "#f59e0b",
  queued: "#a78bfa",
  running: "#3b82f6",
  completed: "#10b981",
  failed: "#ef4444",
};

export const DisplayNode = memo(function DisplayNode({
  id: nodeId,
  data,
  selected,
}: NodeProps) {
  const d = data as unknown as DisplayNodeData;
  const isImageViewer = d.nodeType === "ImageViewer";
  const statusColor = d.status ? STATUS_COLORS[d.status] : undefined;
  const isRunning = d.status === "running";
  const accentColor = "#22c55e";
  const softAccent = "rgba(34,197,94,0.10)";
  const glowAccent = "rgba(34,197,94,0.30)";

  const thumbnailSrc = useMemo(() => {
    if (!d.thumbnail) return null;
    if (d.thumbnail.startsWith("data:") || d.thumbnail.startsWith("http")) {
      return d.thumbnail;
    }
    return `data:image/png;base64,${d.thumbnail}`;
  }, [d.thumbnail]);

  return (
    <div
      className="comfy-node"
      style={{
        borderColor: d.status === "failed"
          ? "#ef4444"
          : selected
            ? accentColor
            : "#2a2a4a",
        borderWidth: d.status === "failed" ? 2 : 1,
        boxShadow: d.status === "failed"
          ? "0 0 20px rgba(239,68,68,0.30), 0 2px 12px rgba(0,0,0,0.4)"
          : selected
            ? `0 0 20px ${glowAccent}, 0 2px 12px rgba(0,0,0,0.4)`
            : isRunning
              ? `0 0 16px ${glowAccent}, 0 2px 8px rgba(0,0,0,0.3)`
              : "0 2px 8px rgba(0,0,0,0.3)",
        animation: isRunning ? "node-pulse 1.5s ease-in-out infinite" : "none",
        minWidth: 160,
        maxWidth: 220,
      }}
    >
      {/* 色条 */}
      <div style={{ height: 2, background: accentColor, flexShrink: 0 }} />

      {/* 头部 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 8px",
          fontSize: 10.5,
          fontWeight: 600,
          color: "#c8c8d4",
          borderBottom: "1px solid #1f1f35",
          background: d.status === "failed" ? "rgba(239,68,68,0.08)" : undefined,
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            flexShrink: 0,
            background: statusColor ?? "#454c5e",
            boxShadow: statusColor ? `0 0 5px ${statusColor}` : undefined,
            animation: isRunning ? "status-blink 0.8s ease-in-out infinite" : "none",
          }}
        />
        <span style={{ opacity: 0.7 }}>{isImageViewer ? "🖼️" : "🖼️"}</span>
        <span style={{ flex: 1 }}>{d.label}</span>
      </div>

      {/* 输入端口 */}
      <Handle
        type="target"
        position={Position.Left}
        id={isImageViewer ? "image" : "images"}
        title={`${isImageViewer ? "image" : "images"}: ${isImageViewer ? "IMAGE" : "IMAGE_BATCH"}`}
        className="comfy-handle"
        style={{
          top: "50%",
          background: accentColor,
          borderColor: accentColor,
        }}
      />

      {/* 展示区 */}
      <div
        style={{
          padding: "6px 8px",
          minHeight: 72,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0d0d1a",
          overflow: "hidden",
          cursor: thumbnailSrc ? "pointer" : "default",
        }}
      >
        {thumbnailSrc ? (
          <img
            src={thumbnailSrc}
            alt="preview"
            style={{
              maxWidth: "100%",
              maxHeight: 128,
              objectFit: "contain",
              imageRendering: "pixelated",
              borderRadius: 3,
            }}
            onClick={() => d.onThumbnailClick?.(nodeId)}
          />
        ) : (
          <span style={{ fontSize: 10, color: "#454c5e", padding: "12px 0", textAlign: "center" }}>
            {isRunning
              ? "运行中..."
              : d.status === "queued"
                ? "排队中..."
                : d.status === "pending"
                  ? "等待中..."
                  : d.status === "completed"
                    ? "已完成"
                    : d.status === "failed"
                      ? "失败"
                      : "等待上游结果"}
          </span>
        )}
      </div>

      {/* 错误信息 */}
      {d.status === "failed" && d.error && (
        <div
          style={{
            fontSize: 10,
            color: "#ef4444",
            padding: "4px 6px",
            margin: "0 8px 6px",
            background: "rgba(239,68,68,0.08)",
            borderRadius: 3,
            border: "1px solid rgba(239,68,68,0.2)",
            wordBreak: "break-all",
            lineHeight: 1.3,
          }}
        >
          {d.error.length > 80 ? d.error.slice(0, 80) + "…" : d.error}
        </div>
      )}
    </div>
  );
});

export default DisplayNode;

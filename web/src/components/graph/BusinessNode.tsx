import { memo, useMemo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { FiUser, FiCompass, FiPlay, FiZap, FiImage, FiBox } from "react-icons/fi";
import { api } from "@/api/client";
import type { NodeSchema } from "@/api/types";

export interface BusinessNodeData extends Record<string, unknown> {
  label: string;
  nodeType: string;
  params: Record<string, unknown>;
  schema?: NodeSchema;
  collapsed?: boolean;
  status?: "idle" | "pending" | "queued" | "running" | "completed" | "failed";
  cacheHit?: boolean;
  thumbnail?: string | null;
  assetId?: string | null;
  url?: string | null;
  error?: string | null;
  onParamChange?: (nodeId: string, params: Record<string, unknown>) => void;
  onCollapsedChange?: (nodeId: string, collapsed: boolean) => void;
}

/* ====================== 类型颜色映射 ====================== */
const TYPE_COLORS: Record<string, { accent: string; soft: string; glow: string }> = {
  CharacterMaster:  { accent: "#3b82f6", soft: "rgba(59,130,246,0.10)", glow: "rgba(59,130,246,0.30)" },
  DirectionVariant:{ accent: "#10b981", soft: "rgba(16,185,129,0.10)", glow: "rgba(16,185,129,0.30)" },
  AnimationSprite: { accent: "#f59e0b", soft: "rgba(245,158,11,0.10)", glow: "rgba(245,158,11,0.30)" },
  SkillVFX:        { accent: "#6366f1", soft: "rgba(99,102,241,0.10)", glow: "rgba(99,102,241,0.30)" },
  ImageFusion:     { accent: "#ec4899", soft: "rgba(236,72,153,0.10)", glow: "rgba(236,72,153,0.30)" },
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#f59e0b",
  queued: "#a78bfa",
  running: "#3b82f6",
  completed: "#10b981",
  failed: "#ef4444",
};

const TYPE_ICONS: Record<string, React.ReactNode> = {
  CharacterMaster:  <FiUser size={14} />,
  DirectionVariant: <FiCompass size={14} />,
  AnimationSprite:  <FiPlay size={14} />,
  SkillVFX:         <FiZap size={14} />,
  ImageFusion:      <FiImage size={14} />,
};

const TYPE_I18N_KEYS: Record<string, string> = {
  CharacterMaster:  "graph.characterMaster",
  DirectionVariant: "graph.directionVariant",
  AnimationSprite:  "graph.animationSprite",
  SkillVFX:         "graph.skillVFX",
  ImageFusion:      "graph.imageFusion",
};

/* ====================== BusinessNode ====================== */

export const BusinessNode = memo(function BusinessNode({
  id: _nodeId,
  data,
  selected,
}: NodeProps) {
  const { t } = useTranslation();
  const d = data as unknown as BusinessNodeData;
  const schemasQuery = useQuery({
    queryKey: ["node-schemas", "pipeline"],
    queryFn: () => api.listNodesByCategory("pipeline"),
    staleTime: 60_000,
  });
  const schema = d.schema ?? schemasQuery.data?.find((s) => s.type === d.nodeType);
  const baseColors = TYPE_COLORS[d.nodeType] ?? TYPE_COLORS.CharacterMaster;
  const colors = schema?.color
    ? { accent: schema.color, soft: `${schema.color}1a`, glow: `${schema.color}4d` }
    : baseColors;
  const fallbackMeta = { icon: TYPE_ICONS[d.nodeType] ?? <FiBox size={14} />, label: t(TYPE_I18N_KEYS[d.nodeType] ?? "graph.unknown", d.nodeType) as string };
  const meta = { icon: schema?.icon ?? fallbackMeta.icon, label: schema?.label ?? fallbackMeta.label };
  const inputPorts = schema?.inputs ?? (d.nodeType === "CharacterMaster" ? {} : { image: "IMAGE" });
  const outputPorts = schema?.outputs ?? (d.nodeType === "DirectionVariant" || d.nodeType === "AnimationSprite" || d.nodeType === "SkillVFX" ? { images: "IMAGE_BATCH" } : { image: "IMAGE" });
  const statusColor = d.status ? STATUS_COLORS[d.status] : undefined;
  const isRunning = d.status === "running";

  const thumbnailSrc = useMemo(() => {
    if (!d.thumbnail) return null;
    if (d.thumbnail.startsWith("data:") || d.thumbnail.startsWith("http")) {
      return d.thumbnail;
    }
    return `data:image/png;base64,${d.thumbnail}`;
  }, [d.thumbnail]);

  const hasPreview = thumbnailSrc || d.status === "running" || d.status === "pending" || d.status === "queued" || d.status === "failed";

  return (
    <div
      className="comfy-node"
      style={{
        minWidth: 140,
        borderColor: d.status === "failed"
          ? "#ef4444"
          : selected
            ? colors.accent
            : "#2a2a4a",
        borderWidth: d.status === "failed" ? 2 : 1,
        boxShadow: d.status === "failed"
          ? "0 0 20px rgba(239,68,68,0.30), 0 2px 12px rgba(0,0,0,0.4)"
          : selected
            ? `0 0 20px ${colors.glow}, 0 2px 12px rgba(0,0,0,0.4)`
            : isRunning
              ? `0 0 16px ${colors.glow}, 0 2px 8px rgba(0,0,0,0.3)`
              : "0 2px 8px rgba(0,0,0,0.3)",
        animation: isRunning ? "node-pulse 1.5s ease-in-out infinite" : "none",
      }}
    >
      {/* 类型色条 */}
      <div style={{ height: 2, background: colors.accent, flexShrink: 0 }} />

      {/* 头部 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "6px 10px",
          fontSize: 11,
          fontWeight: 600,
          color: "#c8c8d4",
          userSelect: "none",
          background: d.status === "failed" ? "rgba(239,68,68,0.08)" : undefined,
        }}
      >
        {/* 状态灯 */}
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
        <span style={{ opacity: 0.7, fontSize: 13 }}>{meta.icon}</span>
        <span style={{ flex: 1 }}>{meta.label}</span>
        {d.cacheHit && (
          <span
            style={{
              fontSize: 9,
              padding: "1px 5px",
              borderRadius: 3,
              background: colors.soft,
              color: colors.accent,
            }}
          >
            {t("graph.cached", "缓存")}
          </span>
        )}
      </div>

      {/* 预览区 - 内置展示 */}
      {hasPreview && (
        <div
          style={{
            padding: thumbnailSrc ? "4px 8px" : "6px 8px",
            minHeight: thumbnailSrc ? undefined : 40,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#0d0d1a",
            borderTop: "1px solid #1f1f35",
            overflow: "hidden",
          }}
        >
          {thumbnailSrc ? (
            <img
              src={thumbnailSrc}
              alt="preview"
              style={{
                maxWidth: "100%",
                maxHeight: 96,
                objectFit: "contain",
                imageRendering: "pixelated",
                borderRadius: 3,
              }}
            />
          ) : (
            <span style={{ fontSize: 10, color: "#454c5e", textAlign: "center" }}>
              {isRunning
                ? "运行中..."
                : d.status === "queued"
                  ? "排队中..."
                  : d.status === "pending"
                    ? "等待中..."
                    : d.status === "failed"
                      ? "失败"
                      : ""}
            </span>
          )}
        </div>
      )}

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

      {/* 输入端口（左侧） */}
      {Object.entries(inputPorts).map(([port, portType]) => (
        <Handle
          key={`in-${port}`}
          type="target"
          position={Position.Left}
          id={port}
          title={`${port}: ${portType}`}
          className="comfy-handle"
          style={{
            top: "50%",
            background: colors.accent,
            borderColor: colors.accent,
          }}
        />
      ))}

      {/* 输出端口（右侧） */}
      {Object.entries(outputPorts).map(([port, portType]) => (
        <Handle
          key={`out-${port}`}
          type="source"
          position={Position.Right}
          id={port}
          title={`${port}: ${portType}`}
          className="comfy-handle"
          style={{
            top: "50%",
            background: colors.accent,
            borderColor: colors.accent,
          }}
        />
      ))}
    </div>
  );
});

export default BusinessNode;

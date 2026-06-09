import type { DragEvent, ReactElement } from "react";

export type PaletteNodeDef = {
  type: string;
  label?: string;
  color?: string;
  description?: string;
  category?: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
};

const WIDTH = 52;

/* ---------------- inline SVG icons (feather-style) ---------------- */
const iconMap: Record<string, ReactElement> = {
  CharacterMaster: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  ),
  DirectionVariant: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24,7.76 14.12,14.12 7.76,16.24 9.88,9.88 16.24,7.76" />
    </svg>
  ),
  AnimationSprite: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 9h9l-4 7h3L8 22l5-8H8l3-5Z" />
    </svg>
  ),

};

const FALLBACK_NODES: PaletteNodeDef[] = [
  { type: "CharacterMaster", label: "角色母版", color: "#3b82f6", category: "pipeline", description: "根据规格书和角色模板生成角色基础形象", inputs: {}, outputs: { image: "IMAGE" } },
  { type: "DirectionVariant", label: "方向变体", color: "#10b981", category: "pipeline", description: "从角色母版生成多个方向的变体素材（↓↑←→）", inputs: { image: "IMAGE" }, outputs: { images: "IMAGE_BATCH" } },
  { type: "AnimationSprite", label: "动画精灵", color: "#f59e0b", category: "pipeline", description: "基于上游素材生成指定动作序列帧动画", inputs: { image: "IMAGE" }, outputs: { images: "IMAGE_BATCH" } },
];

export function NodePalette() {
  const nodes = FALLBACK_NODES;
  const onDragStart = (
    e: DragEvent<HTMLDivElement>,
    nodeDef: PaletteNodeDef
  ) => {
    e.dataTransfer.setData("application/node-type", nodeDef.type);
    e.dataTransfer.effectAllowed = "move";
  };

  return (
    <div
      className="flex flex-col h-full border-r shrink-0"
      style={{
        width: WIDTH,
        borderColor: "var(--line)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex flex-col items-center gap-1 py-2 h-full overflow-y-auto">
        {nodes.map((node) => (
          <div
            key={node.type}
            draggable
            onDragStart={(e) => onDragStart(e, node)}
            className="w-9 h-9 rounded-lg flex items-center justify-center cursor-grab active:cursor-grabbing hover:scale-110 transition-transform"
            style={{
              background: "#0d0f18",
              border: "1px solid #1a1d2e",
            }}
            title={`${node.label ?? node.type} — ${node.description}`}
          >
            <span style={{ color: node.color ?? "#6366f1", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {iconMap[node.type] ?? (
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                </svg>
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import type { DragEvent } from "react";
import { api } from "@/api/client";
import type { NodeSchema } from "@/api/types";

export type PaletteNodeDef = NodeSchema & {
  label?: string;
  icon?: string;
  color?: string;
  description?: string;
};

const FALLBACK_NODES: PaletteNodeDef[] = [
  { type: "CharacterMaster", label: "角色母版", icon: "👤", color: "#3b82f6", category: "pipeline", description: "根据规格书和角色模板生成角色基础形象", inputs: {}, outputs: { image: "IMAGE" }, params: [] },
  { type: "DirectionVariant", label: "方向变体", icon: "🧭", color: "#10b981", category: "pipeline", description: "从角色母版生成多个方向的变体素材（↓↑←→）", inputs: { image: "IMAGE" }, outputs: { images: "IMAGE_BATCH" }, params: [] },
  { type: "AnimationSprite", label: "动画精灵", icon: "🏃", color: "#f59e0b", category: "pipeline", description: "基于上游素材生成指定动作序列帧动画", inputs: { image: "IMAGE" }, outputs: { images: "IMAGE_BATCH" }, params: [] },
  { type: "SkillVFX", label: "技能特效", icon: "💥", color: "#6366f1", category: "pipeline", description: "根据 VFX 模板生成技能特效序列帧", inputs: { image: "IMAGE" }, outputs: { images: "IMAGE_BATCH" }, params: [] },
  { type: "ImageFusion", label: "图片融合", icon: "🖼️", color: "#ec4899", category: "pipeline", description: "将多张图片/模板融合生成合成图", inputs: { images: "IMAGE_BATCH" }, outputs: { image: "IMAGE" }, params: [] },
  { type: "ImageViewer", label: "图片查看", icon: "🖼️", color: "#22c55e", category: "display", description: "展示上游单张生成结果图片，可手动连线到任意输出节点", inputs: { image: "IMAGE" }, outputs: {}, params: [] },
  { type: "GalleryViewer", label: "图库查看", icon: "🖼️", color: "#22c55e", category: "display", description: "展示上游批量生成结果（序列帧），可手动连线到任意输出节点", inputs: { images: "IMAGE_BATCH" }, outputs: {}, params: [] },
];

const MAX_VISIBLE_BEFORE_SCROLL = 5;

export function NodePalette() {
  const { t } = useTranslation();
  const [expandedType, setExpandedType] = useState<string | null>(null);
  const nodesQuery = useQuery({
    queryKey: ["node-schemas", "pipeline"],
    queryFn: () => api.listNodesByCategory("pipeline"),
    staleTime: 60_000,
  });
  const nodes = nodesQuery.data?.length ? nodesQuery.data : FALLBACK_NODES;

  const onDragStart = (
    e: DragEvent<HTMLDivElement>,
    nodeDef: PaletteNodeDef
  ) => {
    e.dataTransfer.setData("application/node-type", nodeDef.type);
    e.dataTransfer.effectAllowed = "move";
  };

  return (
    <div className="flex flex-col shrink-0">
      <div
        className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider border-b flex items-center justify-between"
        style={{ color: "var(--txt-2)", borderColor: "var(--line-soft)" }}
      >
        <span>{t("graph.palette", "管线节点")}</span>
        <span className="text-[9px] font-normal" style={{ color: "var(--txt-3)" }}>
          {t("graph.dragToAdd", "拖入画布")}
        </span>
      </div>
      <div
        className="overflow-y-auto px-2 py-1.5 flex flex-col gap-1.5"
        style={{ maxHeight: nodes.length > MAX_VISIBLE_BEFORE_SCROLL ? 280 : "none" }}
      >
        {nodes.map((node) => {
          const isExpanded = expandedType === node.type;
          return (
            <div
              key={node.type}
              draggable
              onDragStart={(e) => onDragStart(e, node)}
              onClick={() => setExpandedType(isExpanded ? null : node.type)}
              className="group cursor-grab active:cursor-grabbing select-none rounded-lg border transition-all hover:-translate-y-px"
              style={{
                borderColor: isExpanded ? (node.color ?? "#6366f1") : "#22263a",
                background: "#0d0f18",
                boxShadow: "0 1px 6px rgba(0,0,0,0.25)",
              }}
              title={node.description}
            >
              <div style={{ height: 2, borderRadius: "8px 8px 0 0", background: node.color ?? "#6366f1" }} />
              <div className="px-2 py-1.5 flex items-center gap-2">
                <span
                  className="w-5 h-5 rounded flex items-center justify-center shrink-0 text-[11px]"
                  style={{ background: `${node.color ?? "#6366f1"}1a`, color: node.color ?? "#6366f1" }}
                >
                  {node.icon ?? "📦"}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--txt-0)" }}>
                    {node.label ?? node.type}
                  </div>
                </div>
                <span className="text-[9px] shrink-0" style={{ color: "var(--txt-3)" }}>
                  {isExpanded ? "▲" : "▼"}
                </span>
              </div>
              {isExpanded && (
                <div className="px-2 pb-2 border-t" style={{ borderColor: "#1a1d2e" }}>
                  <div className="mt-1.5 text-[10px] leading-snug" style={{ color: "var(--txt-3)" }}>
                    {node.description}
                  </div>
                  <div className="mt-1.5 flex gap-1 flex-wrap">
                    {Object.keys(node.inputs).length > 0 && (
                      <span className="tech-chip" style={{ fontSize: 8, padding: "1px 4px" }}>
                        IN {Object.keys(node.inputs).length}
                      </span>
                    )}
                    <span className="tech-chip tech-chip-acc" style={{ fontSize: 8, padding: "1px 4px", color: node.color ?? "#6366f1" }}>
                      OUT {Object.keys(node.outputs).length}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {nodesQuery.isError && (
          <div className="px-2 py-1 text-[10px]" style={{ color: "#f59e0b" }}>
            {t("graph.nodeSchemaFallback", "节点 Schema 加载失败，使用本地默认列表")}
          </div>
        )}
      </div>
    </div>
  );
}

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Button } from "@/components/ui/Button";
import type { PipelineGraphModel } from "@/api/types";

interface PresetPipelinesProps {
  onLoad: (graph: PipelineGraphModel) => void;
}

export function PresetPipelines({ onLoad }: PresetPipelinesProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);

  const presetsQuery = useQuery({
    queryKey: ["graph-presets"],
    queryFn: () => api.listGraphPresets(),
    staleTime: 60_000,
    enabled: open,
  });

  const handleSelect = async (presetId: string) => {
    setLoading(presetId);
    try {
      const graph = await api.getGraphPreset(presetId);
      onLoad(graph);
      setOpen(false);
    } catch (e) {
      console.error("Load preset failed", e);
    } finally {
      setLoading(null);
    }
  };

  if (!open) {
    return (
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        {t("graph.presets", "预设管线")}
      </Button>
    );
  }

  const presets = presetsQuery.data?.presets ?? [];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={() => setOpen(false)}
      />
      {/* Modal */}
      <div
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[480px] max-h-[70vh] rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{
          background: "var(--bg-mod, #1e1e2e)",
          border: "1px solid var(--line)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-3.5 border-b shrink-0"
          style={{ borderColor: "var(--line-soft)" }}
        >
          <h3 className="text-[13px] font-semibold text-txt-0">
            {t("graph.presets", "预设管线")}
          </h3>
          <button
            onClick={() => setOpen(false)}
            className="w-7 h-7 flex items-center justify-center rounded-md text-txt-2 hover:text-txt-0 hover:bg-bg-3 transition"
          >
            ✕
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-3">
          {presetsQuery.isLoading && (
            <div className="py-8 text-center text-[12px] text-txt-3">
              {t("common.loading", "加载中...")}
            </div>
          )}
          {!presetsQuery.isLoading && presets.length === 0 && (
            <div className="py-8 text-center text-[12px] text-txt-3">
              {t("graph.noPresets", "暂无预设管线")}
            </div>
          )}
          {presets.map((p) => (
            <button
              key={p.id}
              disabled={loading === p.id}
              onClick={() => handleSelect(p.id)}
              className="text-left p-4 rounded-lg border transition-all hover:brightness-110 disabled:opacity-60 disabled:cursor-wait"
              style={{
                background: "var(--bg-1)",
                borderColor: "var(--line-soft)",
              }}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[12.5px] font-semibold text-txt-0">
                  {p.name}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: "var(--acc-soft)", color: "var(--acc)" }}>
                  {p.node_count} {t("graph.nodes", "节点")}
                </span>
              </div>
              {p.description && (
                <p className="text-[11px] text-txt-2 mb-2 leading-relaxed">
                  {p.description}
                </p>
              )}
              {p.tags && p.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {p.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{
                        background: "var(--bg-3)",
                        color: "var(--txt-3)",
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>

        {/* Footer */}
        <div
          className="px-5 py-3 border-t shrink-0 flex justify-end"
          style={{ borderColor: "var(--line-soft)" }}
        >
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            {t("common.cancel", "取消")}
          </Button>
        </div>
      </div>
    </>
  );
}

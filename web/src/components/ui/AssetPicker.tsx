import { useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { Segment } from "./Segment";

interface Props {
  open: boolean;
  onClose: () => void;
  onPick: (asset: AssetItem) => void;
  multi?: boolean;
}

type Filter = "all" | "uploaded" | "generated" | "favorite";

export function AssetPicker({ open, onClose, onPick, multi: _ }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("all");

  const { data, isLoading } = useQuery({
    queryKey: ["asset-picker", filter],
    queryFn: () => {
      const p: any = { limit: 60 };
      if (filter === "uploaded" || filter === "generated") p.source = filter;
      if (filter === "favorite") p.favorite = true;
      return api.listAssets(p);
    },
    enabled: open,
  });

  if (!open) return null;

  // 用 Portal 渲染到 body，避免被父级 overflow/transform 截断
  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-[820px] max-h-[80vh] flex flex-col rounded-l border border-line bg-bg-1 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-5 py-4 border-b border-line">
          <div className="text-[14px] font-semibold text-txt-0">
            {t("picker.title")}
          </div>
          <Segment
            className="ml-auto !w-[360px]"
            items={[
              { value: "all", label: t("picker.all") },
              { value: "uploaded", label: t("picker.uploaded") },
              { value: "generated", label: t("picker.generated") },
              { value: "favorite", label: t("picker.favorite") },
            ]}
            value={filter}
            onChange={(v) => setFilter(v as Filter)}
          />
          <button
            onClick={onClose}
            className="text-txt-2 hover:text-txt-0 px-2 h-7"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && (
            <div className="text-center py-12 text-txt-3 text-[12px]">
              {t("common.loading")}
            </div>
          )}
          {data && data.items.length === 0 && (
            <div className="text-center py-12 text-txt-3 text-[12px]">
              {t("common.empty")}
            </div>
          )}
          {data && data.items.length > 0 && (
            <div className="grid grid-cols-5 gap-3">
              {data.items.map((a) => (
                <button
                  key={a.id}
                  onClick={() => {
                    onPick(a);
                    onClose();
                  }}
                  className="group relative aspect-square overflow-hidden rounded-m border border-line bg-bg-0 hover:border-[var(--acc)] transition-colors"
                >
                  {a.thumbnail || a.uri ? (
                    <img
                      src={a.thumbnail || a.uri}
                      alt={a.id}
                      className="w-full h-full object-cover pixelated"
                    />
                  ) : (
                    <div className="w-full h-full grid place-items-center text-txt-3 text-[10px]">
                      no preview
                    </div>
                  )}
                  <div className="absolute top-1.5 left-1.5">
                    <span
                      className="text-[8.5px] font-mono px-1.5 py-0.5 rounded text-black"
                      style={{
                        background:
                          a.source === "uploaded"
                            ? "var(--cyan)"
                            : a.source === "generated"
                            ? "var(--acc)"
                            : "var(--violet)",
                      }}
                    >
                      {a.source}
                    </span>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 px-2 py-1 bg-gradient-to-t from-black/80 text-[9.5px] font-mono text-white text-left">
                    {a.width}×{a.height}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

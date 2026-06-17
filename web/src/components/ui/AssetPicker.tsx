import { useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { Button } from "./Button";
import { Segment } from "./Segment";

interface Props {
  open: boolean;
  onClose: () => void;
  onPick: (asset: AssetItem) => void;
  multi?: boolean;
  filterType?: string;   // 按素材类型预筛选（image/video/audio/text）
}

type Filter = "all" | "upload" | "image" | "audio" | "text" | "favorite";

const PAGE_SIZE = 30;

/** 分类显示标签 */
function badgeLabel(a: AssetItem): string {
  if (a.type === "video") return "视频";
  if (a.type === "audio") return "音频";
  if (a.type === "text") return "文本";
  if (a.source === "uploaded") return "上传";
  return "图片";
}

/** 分类 badge 底色 */
function badgeColor(a: AssetItem): string {
  if (a.type === "video") return "var(--violet)";
  if (a.type === "audio") return "var(--orange)";
  if (a.type === "text") return "var(--cyan)";
  if (a.source === "uploaded") return "var(--cyan)";
  return "var(--acc)";
}

export function AssetPicker({ open, onClose, onPick, multi: _, filterType }: Props) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>("all");
  const [page, setPage] = useState(0);

  const actualFilterType = filterType || "";
  const queryKey = ["asset-picker", filter, page, actualFilterType];

  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => {
      const p: any = { limit: PAGE_SIZE, offset: page * PAGE_SIZE };
      if (filter === "upload") p.source = "uploaded";
      else if (filter === "image") p.source = "generated,derived,ai_processed";
      else if (filter === "audio") p.type = "audio";
      else if (filter === "text") p.type = "text";
      if (filter === "favorite") p.favorite = true;
      // 当有 filterType 预筛选且用户未手动选择分类时，应用预筛选
      if (actualFilterType && filter === "all") {
        p.type = actualFilterType;
      }
      return api.listAssets(p);
    },
    enabled: open,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const resetAndSetFilter = (v: string) => {
    setFilter(v as Filter);
    setPage(0);
  };

  if (!open) return null;

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
            className="ml-auto !w-[440px]"
            items={[
              { value: "all", label: t("picker.all") },
              { value: "upload", label: t("picker.upload", "上传") },
              { value: "image", label: t("picker.image", "图片") },
              { value: "audio", label: t("picker.audio", "音频") },
              { value: "text", label: t("picker.text", "文本") },
              { value: "favorite", label: t("picker.favorite") },
            ]}
            value={filter}
            onChange={(v) => resetAndSetFilter(v)}
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
                  {a.type === "video" ? (
                    <video src={a.uri} className="w-full h-full object-cover" muted preload="metadata" />
                  ) : a.type === "audio" ? (
                    <div className="w-full h-full flex flex-col items-center justify-center bg-bg-0 p-2">
                      <div className="text-xl mb-1">🎵</div>
                      <div className="text-[9px] text-txt-3 text-center leading-tight">
                        {a.mime_type || "audio"}
                      </div>
                    </div>
                  ) : a.type === "text" ? (
                    <div className="w-full h-full flex flex-col items-start p-2 bg-bg-0">
                      <div className="text-[9px] text-txt-2 leading-tight whitespace-pre-wrap line-clamp-5 text-left flex-1 overflow-hidden">
                        {a.text_preview || "(empty)"}
                      </div>
                    </div>
                  ) : a.thumbnail || a.uri ? (
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
                      style={{ background: badgeColor(a) }}
                    >
                      {badgeLabel(a)}
                    </span>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 px-2 py-1 bg-gradient-to-t from-black/80 text-[9.5px] font-mono text-white text-left">
                    {a.type === "video" ? "MP4" : a.type === "audio" ? "AUDIO" : a.type === "text" ? "TXT" : `${a.width ?? "-"}×${a.height ?? "-"}`}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* 分页 */}
          {data && totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-4 pt-3 border-t border-line">
              <Button
                size="xs" variant="ghost" disabled={page === 0}
                onClick={() => setPage(0)}
              >
                ««
              </Button>
              <Button
                size="xs" variant="ghost" disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                ‹
              </Button>
              <span className="text-[11px] text-txt-3 px-2 tabular-nums">
                {page + 1} / {totalPages}
              </span>
              <Button
                size="xs" variant="ghost" disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
              >
                ›
              </Button>
              <Button
                size="xs" variant="ghost" disabled={page >= totalPages - 1}
                onClick={() => setPage(totalPages - 1)}
              >
                »»
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

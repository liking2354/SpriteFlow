import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Segment } from "@/components/ui/Segment";
import { GroupSidebar } from "@/components/GroupSidebar";
import { AssetPreviewModal } from "@/components/AssetPreviewModal";
import { useConfirm } from "@/components/ui/Confirm";

type SourceFilter = "all" | "uploaded" | "generated" | "derived" | "video";

async function downloadAssetFile(asset: AssetItem) {
  const ext = asset.type === "video" ? "mp4" : "png";
  const filename = `${asset.id}.${ext}`;
  const res = await fetch(`/api/assets/${encodeURIComponent(asset.id)}/raw`);
  if (!res.ok) throw new Error("download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function AssetsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const fileRef = useRef<HTMLInputElement>(null);

  const PAGE_SIZE = 24;
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [source, setSource] = useState<SourceFilter>("all");
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewAsset, setPreviewAsset] = useState<AssetItem | null>(null);

  const list = useQuery({
    queryKey: ["assets", source, groupFilter, page],
    queryFn: () =>
      api.listAssets({
        source: source === "all" ? undefined : source === "video" ? undefined : source,
        type: source === "video" ? "video" : undefined,
        group_id: groupFilter ?? undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  const total = list.data?.total ?? 0;

  const upload = useMutation({
    mutationFn: ({ file }: { file: File }) =>
      api.uploadAsset(file, "", undefined, groupFilter ?? undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assets"] }),
  });

  const batchDelete = useMutation({
    mutationFn: (ids: string[]) => api.batchDeleteAssets(ids),
    onSuccess: () => {
      setSelectedIds(new Set());
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => api.deleteAsset(id),
    onSuccess: () => {
      setPreviewAsset(null);
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    upload.mutate({ file: f });
    e.target.value = "";
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!list.data?.items.length) return;
    if (selectedIds.size === list.data.items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(list.data.items.map((a) => a.id)));
    }
  };

  const handleClickAsset = (asset: AssetItem, e: React.MouseEvent) => {
    // Cmd/Ctrl + click = 多选
    if (e.metaKey || e.ctrlKey) {
      toggleSelect(asset.id);
      return;
    }
    // 已处于多选模式时单击切换
    if (selectedIds.size > 0) {
      toggleSelect(asset.id);
      return;
    }
    // 普通单击 = 预览
    setPreviewAsset(asset);
  };


  return (
    <div className="flex gap-0 h-[calc(100vh-8rem)]">
      {/* 左侧分组边栏 */}
      <div className="w-[180px] flex-shrink-0 border-r border-line bg-bg-1 rounded-l-lg overflow-hidden">
        <GroupSidebar selectedGroupId={groupFilter} onSelect={(gid) => { setGroupFilter(gid); setPage(0); }} />
      </div>

      {/* 主区域 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden rounded-l border border-line bg-bg-1"
        style={{
          boxShadow: "0 1px 0 rgba(255,255,255,0.02) inset, 0 12px 32px rgba(0,0,0,0.25)",
        }}
      >
        {/* 标题栏 */}
        <div className="relative z-[1] flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-[var(--line-soft)] flex-shrink-0">
          <div>
            <div className="text-[14px] font-semibold text-txt-0 tracking-[0.2px]">
              {t("assets.title")}
            </div>
            <div className="text-[11.5px] text-txt-2 mt-1">{t("assets.subtitle")}</div>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="image/*,video/*"
              className="hidden"
              onChange={onFile}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => fileRef.current?.click()}
              loading={upload.isPending}
            >
              ↑ {t("assets.upload.button")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => list.refetch()}>
              ⟳ {t("common.refresh")}
            </Button>
          </div>
        </div>

        {/* 可滚动内容区 */}
        <div className="flex-1 min-h-0 overflow-hidden p-5 flex flex-col">
          {/* 筛选栏 */}
          <div className="flex items-center gap-3 mb-3 flex-shrink-0">
            <Segment
              items={[
                { value: "all", label: t("assets.filter.all") },
                { value: "uploaded", label: t("assets.filter.uploaded") },
                { value: "generated", label: t("assets.filter.generated") },
                { value: "derived", label: t("assets.filter.derived") },
                { value: "video", label: t("assets.filter.video", "视频") },
              ]}
              value={source}
              onChange={(v) => { setSource(v); setPage(0); setSelectedIds(new Set()); }}
              className="flex-shrink-0"
            />
            {list.data && (
              <span className="text-[11px] text-txt-3 flex-shrink-0">
                {t("assets.count", "共")} {total} {t("assets.countUnit", "个素材")}
              </span>
            )}
          </div>

          {/* 批量操作栏 */}
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-bg-2 rounded-m border border-line flex-shrink-0">
              <span className="text-[12px] text-txt-2">
                {t("assets.selected", "已选")} {selectedIds.size} {t("assets.selectedUnit", "项")}
              </span>
              <Button
                size="xs"
                variant="ghost"
                onClick={toggleSelectAll}
              >
                {selectedIds.size === (list.data?.items.length ?? 0) ? "取消全选" : t("assets.selectAll", "全选")}
              </Button>
              <div className="flex-1" />
              <Button
                size="xs"
                variant="ghost"
                className="text-red-400"
                loading={batchDelete.isPending}
                onClick={async () => {
                  if (await confirm({ message: t("assets.deleteConfirm", "确定删除选中的素材？"), variant: "danger" }))
                    batchDelete.mutate(Array.from(selectedIds));
                }}
              >
                🗑 {t("common.delete")} ({selectedIds.size})
              </Button>
            </div>
          )}

          {/* 素材网格（可滚动） */}
          <div
            className="flex-1 min-h-0 overflow-y-auto pr-1 mb-3"
          >
            {list.isLoading && (
              <div className="text-center py-12 text-txt-3">{t("common.loading")}</div>
            )}

            {list.data && list.data.items.length === 0 && (
              <div className="text-center py-12 text-txt-3">{t("assets.empty")}</div>
            )}

            {list.data && list.data.items.length > 0 && (
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7 2xl:grid-cols-8 gap-2">
                {list.data.items.map((a) => {
                  const sel = selectedIds.has(a.id);
                  const isVideo = a.type === "video";
                  return (
                    <button
                      key={a.id}
                      onClick={(e) => handleClickAsset(a, e)}
                      className={`group relative aspect-square overflow-hidden rounded-m border bg-bg-0 transition-all ${
                        sel
                          ? "border-[var(--acc)] ring-1 ring-[var(--acc)]/40"
                          : "border-line hover:border-[#2f3647]"
                      }`}
                    >
                      {isVideo ? (
                        <>
                          <video
                            src={a.uri}
                            className="w-full h-full object-cover"
                            muted
                            preload="metadata"
                          />
                          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            <div className="w-8 h-8 rounded-full bg-black/60 flex items-center justify-center text-white text-sm">
                              ▶
                            </div>
                          </div>
                        </>
                      ) : a.thumbnail || a.uri ? (
                        <img
                          src={a.thumbnail || a.uri}
                          alt={a.id}
                          className="w-full h-full object-cover pixelated"
                          loading="lazy"
                        />
                      ) : (
                        <div className="w-full h-full grid place-items-center text-txt-3 text-[9px]">
                          no preview
                        </div>
                      )}

                      {/* 选中标记 */}
                      <div
                        className={`absolute top-1 right-1 w-4 h-4 rounded border-2 flex items-center justify-center transition-all ${
                          sel
                            ? "bg-[var(--acc)] border-[var(--acc)] text-white"
                            : "border-white/30 bg-black/20 opacity-0 group-hover:opacity-100"
                        }`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSelect(a.id);
                        }}
                      >
                        {sel && <span className="text-[8px] leading-none">✓</span>}
                      </div>

                      {/* 来源 + 尺寸 */}
                      <div className="absolute top-1 left-1 flex gap-0.5">
                        <span className="text-[8px] font-mono px-1 py-0.5 rounded text-white"
                          style={{
                            background:
                              a.source === "uploaded" ? "var(--cyan)" :
                              a.source === "generated" ? "var(--acc)" :
                              a.source === "ai_processed" ? "var(--orange)" : "var(--violet)",
                            color: "#001",
                          }}>
                          {a.source}
                        </span>
                        {isVideo && (
                          <span className="text-[7px] font-mono px-1 py-0.5 rounded text-white bg-white/15">
                            🎬
                          </span>
                        )}
                      </div>
                      <div className="absolute bottom-0 left-0 right-0 px-1.5 py-0.5 bg-gradient-to-t from-black/80 text-[8.5px] font-mono text-white text-left">
                        {isVideo ? "MP4" : `${a.width ?? "-"}×${a.height ?? "-"}`}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* 分页栏 */}
          {list.data && totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-2 border-t border-[var(--line-soft)] flex-shrink-0">
              <Button
                size="xs"
                variant="ghost"
                disabled={page === 0}
                onClick={() => { setPage(0); setSelectedIds(new Set()); }}
              >
                ««
              </Button>
              <Button
                size="xs"
                variant="ghost"
                disabled={page === 0}
                onClick={() => { setPage((p) => p - 1); setSelectedIds(new Set()); }}
              >
                ‹
              </Button>
              <span className="text-[11px] text-txt-3 px-2 tabular-nums">
                {page + 1} / {totalPages}
              </span>
              <Button
                size="xs"
                variant="ghost"
                disabled={page >= totalPages - 1}
                onClick={() => { setPage((p) => p + 1); setSelectedIds(new Set()); }}
              >
                ›
              </Button>
              <Button
                size="xs"
                variant="ghost"
                disabled={page >= totalPages - 1}
                onClick={() => { setPage(totalPages - 1); setSelectedIds(new Set()); }}
              >
                »»
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* 预览弹窗 */}
      {previewAsset && (
        <AssetPreviewModal
          asset={previewAsset}
          onClose={() => setPreviewAsset(null)}
          onEdit={(id) => navigate(`/editor?asset=${encodeURIComponent(id)}`)}
          onDownload={async (a) => {
            try { await downloadAssetFile(a); } catch { alert(t("common.error")); }
          }}
          onDelete={async (id) => {
            if (await confirm({ message: t("assets.deleteConfirm", "确定删除？"), variant: "danger" }))
              del.mutate(id);
          }}
        />
      )}
    </div>
  );
}

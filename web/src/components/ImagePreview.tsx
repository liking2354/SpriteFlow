import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { JobItem } from "@/api/types";
import {
  durationSeconds,
  formatDuration,
  useElapsedSeconds,
} from "@/utils/time";

interface Props {
  job: JobItem;
  initialIndex: number;
  onClose: () => void;
  onUseAsRef: (img: { url: string; asset_id?: string; thumbnail?: string | null }) => void;
  onReuse: (job: JobItem) => void;
  onRegenerate: (jobId: string) => void;
}

export function ImagePreview({
  job: initialJob,
  initialIndex,
  onClose,
  onUseAsRef,
  onReuse,
  onRegenerate,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [idx, setIdx] = useState(initialIndex);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // 实时拉父 job（含 pending_children），保证再次生成时占位卡能在缩略图带出现
  const liveJob = useQuery({
    queryKey: ["job-live", initialJob.id],
    queryFn: () => api.getJob(initialJob.id),
    initialData: initialJob,
    refetchInterval: (q) => {
      const d = q.state.data as JobItem | undefined;
      const hasActive =
        !!d?.pending_children?.length ||
        d?.status === "running" ||
        d?.status === "pending";
      return hasActive ? 1500 : false;
    },
  });
  const job = liveJob.data || initialJob;

  useEffect(() => {
    setIdx(initialIndex);
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  }, [initialIndex, initialJob.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight")
        setIdx((i) => Math.min((job.assets?.length || 1) - 1, i + 1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [job.assets?.length, onClose]);

  // 切图重置位置
  useEffect(() => {
    setOffset({ x: 0, y: 0 });
  }, [idx]);

  // 缩放变化时若 zoom==1 也复位
  useEffect(() => {
    if (zoom <= 1) setOffset({ x: 0, y: 0 });
  }, [zoom]);

  const setAssetFav = useMutation({
    mutationFn: ({ id, fav }: { id: string; fav: boolean }) =>
      api.setAssetFavorite(id, fav),
    onMutate: async ({ id, fav }) => {
      // 乐观更新当前 job-live cache
      await queryClient.cancelQueries({ queryKey: ["job-live", initialJob.id] });
      const prev = queryClient.getQueryData<JobItem>(["job-live", initialJob.id]);
      if (prev) {
        queryClient.setQueryData<JobItem>(["job-live", initialJob.id], {
          ...prev,
          assets: prev.assets.map((a) =>
            a.id === id ? { ...a, favorite: fav } : a
          ),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev)
        queryClient.setQueryData(["job-live", initialJob.id], ctx.prev);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["assets-grid"] });
      queryClient.invalidateQueries({ queryKey: ["job-live", initialJob.id] });
    },
  });

  const cur = job.assets[idx];
  if (!cur) {
    // 切到不存在的 idx（例如全部图被删），自动回 0 或关闭
    if (job.assets.length > 0) {
      setIdx(0);
      return null;
    }
    return null;
  }

  const download = () => {
    const a = document.createElement("a");
    a.href = cur.url;
    a.download = `${cur.id}.png`;
    a.target = "_blank";
    a.rel = "noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  // ---------------- 拖拽 ----------------
  const onMouseDown = (e: React.MouseEvent) => {
    if (zoom <= 1) return;
    e.preventDefault();
    setIsDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      ox: offset.x,
      oy: offset.y,
    };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!isDragging || !dragRef.current) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setOffset({ x: dragRef.current.ox + dx, y: dragRef.current.oy + dy });
  };
  const endDrag = () => {
    setIsDragging(false);
    dragRef.current = null;
  };

  const handleRegenerate = () => {
    onRegenerate(job.id);
    // 不关闭，主动刷新一次
    queryClient.invalidateQueries({ queryKey: ["job-live", initialJob.id] });
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
  };

  const cursorClass = zoom > 1 ? (isDragging ? "cursor-grabbing" : "cursor-grab") : "";

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex bg-black/80 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="m-auto w-[min(94vw,1280px)] h-[min(90vh,820px)] grid bg-bg-1 border border-line rounded-l overflow-hidden"
        style={{ gridTemplateColumns: "1fr 320px" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 主预览区 */}
        <div className="relative bg-[#0a0c12] flex flex-col">
          {/* 顶部工具栏 */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-line">
            <div className="flex items-center gap-1 ml-auto">
              <button
                onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
                className="w-7 h-7 grid place-items-center rounded-s border border-line text-txt-1 hover:text-txt-0 hover:border-[#2f3647]"
              >
                −
              </button>
              <span className="text-[11px] font-mono text-txt-2 min-w-[44px] text-center">
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
                className="w-7 h-7 grid place-items-center rounded-s border border-line text-txt-1 hover:text-txt-0 hover:border-[#2f3647]"
              >
                +
              </button>
              <button
                onClick={() => {
                  setZoom(1);
                  setOffset({ x: 0, y: 0 });
                }}
                className="ml-1 px-2 h-7 rounded-s border border-line text-[11px] text-txt-1 hover:text-txt-0 hover:border-[#2f3647]"
              >
                1:1
              </button>
            </div>
            <button
              onClick={onClose}
              className="w-7 h-7 grid place-items-center rounded-s border border-line text-txt-1 hover:text-txt-0 hover:border-[#2f3647]"
            >
              ✕
            </button>
          </div>

          {/* 大图（放大后可拖动） */}
          <div
            className={`flex-1 min-h-0 overflow-hidden p-6 grid place-items-center select-none ${cursorClass}`}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={endDrag}
            onMouseLeave={endDrag}
            onWheel={(e) => {
              if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                const dz = e.deltaY > 0 ? -0.1 : 0.1;
                setZoom((z) => Math.max(0.25, Math.min(4, z + dz)));
              }
            }}
          >
            <img
              src={cur.url}
              alt=""
              draggable={false}
              className="block max-h-[58vh] max-w-full object-contain pixelated pointer-events-none"
              style={{
                transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`,
                transformOrigin: "center",
                transition: isDragging ? "none" : "transform 0.15s ease",
              }}
            />
          </div>

          {/* 缩略图带（含再次生成占位） */}
          {(job.assets.length > 1 || (job.pending_children?.length || 0) > 0) && (
            <div className="flex items-center gap-2 px-4 py-3 border-t border-line">
              <button
                onClick={() => setIdx((i) => Math.max(0, i - 1))}
                disabled={idx === 0}
                className="w-7 h-12 grid place-items-center rounded-s border border-line text-txt-1 hover:text-txt-0 hover:border-[#2f3647] disabled:opacity-30 flex-shrink-0"
              >
                ‹
              </button>
              <div className="flex-1 flex gap-2 overflow-x-auto">
                {job.assets.map((a, i) => (
                  <button
                    key={a.id}
                    onClick={() => setIdx(i)}
                    className={`relative h-14 aspect-square rounded-s overflow-hidden border-2 flex-shrink-0 ${
                      i === idx ? "border-[var(--acc)]" : "border-transparent"
                    }`}
                  >
                    <img
                      src={a.thumbnail || a.url}
                      alt=""
                      className="w-full h-full object-cover pixelated"
                    />
                  </button>
                ))}
                {/* 再次生成占位 */}
                {(job.pending_children || []).map((c) => (
                  <div
                    key={c.job_id}
                    className="relative h-14 aspect-square rounded-s overflow-hidden flex-shrink-0 flex items-center justify-center border-2"
                    style={{
                      borderColor:
                        c.status === "failed"
                          ? "rgba(255,91,110,0.5)"
                          : "var(--acc)",
                      background:
                        c.status === "failed"
                          ? "rgba(255,91,110,0.06)"
                          : "radial-gradient(ellipse at center, var(--acc-soft) 0%, var(--bg-0) 75%)",
                    }}
                  >
                    {c.status === "failed" ? (
                      <span className="text-[var(--red)] text-[14px]">⚠</span>
                    ) : (
                      <div className="relative">
                        <div
                          className="w-6 h-6 rounded-full animate-pulse-glow"
                          style={{
                            background:
                              "conic-gradient(from 0deg, var(--acc), var(--cyan), var(--violet), var(--acc))",
                            filter: "blur(1px)",
                          }}
                        />
                        <div
                          className="absolute inset-0.5 rounded-full"
                          style={{ background: "var(--bg-1)" }}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <button
                onClick={() =>
                  setIdx((i) => Math.min(job.assets.length - 1, i + 1))
                }
                disabled={idx === job.assets.length - 1}
                className="w-7 h-12 grid place-items-center rounded-s border border-line text-txt-1 hover:text-txt-0 hover:border-[#2f3647] disabled:opacity-30 flex-shrink-0"
              >
                ›
              </button>
            </div>
          )}
        </div>

        {/* 右侧详情面板 */}
        <div className="bg-bg-1 border-l border-line overflow-y-auto p-5">
          {/* 操作 */}
          <div className="grid grid-cols-2 gap-2 mb-5">
            <PanelBtn
              icon={cur.favorite ? "★" : "☆"}
              label={t("record.favorite")}
              active={cur.favorite}
              onClick={() =>
                setAssetFav.mutate({ id: cur.id, fav: !cur.favorite })
              }
            />
            <PanelBtn
              icon={
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                </svg>
              }
              label={t("record.download")}
              onClick={download}
            />
          </div>

          <div className="text-[10.5px] text-txt-3 uppercase tracking-[1px] mb-2">
            {t("preview.useAsRef")}
          </div>
          <div className="grid grid-cols-2 gap-2 mb-5">
            <PanelBtn
              icon="🖼"
              label={t("record.useAsRef")}
              onClick={() =>
                onUseAsRef({
                  url: cur.url,
                  asset_id: cur.id,
                  thumbnail: cur.thumbnail,
                })
              }
            />
            <PanelBtn
              icon={
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="m18.5 2.5 3 3L12 15l-4 1 1-4z" />
                </svg>
              }
              label={t("record.reuse")}
              onClick={() => {
                onReuse(job);
                onClose();
              }}
            />
            <PanelBtn
              icon={
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" />
                </svg>
              }
              label={t("record.regenerate")}
              onClick={handleRegenerate}
            />
            <PanelBtn
              icon={
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4z" />
                </svg>
              }
              label={t("editor.open")}
              onClick={() => {
                navigate(`/editor?asset=${encodeURIComponent(cur.id)}`);
                onClose();
              }}
            />
          </div>

          <Detail label={t("preview.mode")} value={t(`generate.modes.${job.mode}`, { defaultValue: job.mode })} />
          <Detail label={t("preview.size")} value={`${cur.width ?? "-"}×${cur.height ?? "-"}`} mono />
          <Detail label={t("preview.model")} value={job.model || "-"} mono />
          <DurationDetail job={job} />
          {job.params?.seed != null && (
            <Detail label={t("preview.seed")} value={String(job.params.seed)} mono />
          )}
          <Detail
            label={t("preview.prompt")}
            value={
              <div className="text-[12px] text-txt-1 whitespace-pre-wrap break-words leading-relaxed">
                {job.prompt}
              </div>
            }
          />

          {(job.ref_assets?.length ?? 0) > 0 && (
            <div className="mt-3">
              <div className="text-[10.5px] text-txt-3 uppercase tracking-[1px] mb-1.5">
                {t("preview.refs")}
              </div>
              <div className="flex flex-wrap gap-2">
                {job.ref_assets.map((r, i) => (
                  <img
                    key={i}
                    src={r.thumbnail || r.url}
                    alt=""
                    className="w-12 h-12 rounded-s object-cover border border-line"
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

function PanelBtn({
  icon,
  label,
  onClick,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center justify-center gap-1 h-16 rounded-s border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[#2f3647] transition-colors"
      style={active ? { color: "var(--amber)", borderColor: "var(--amber)" } : undefined}
    >
      <span className="text-[16px] leading-none">{icon}</span>
      <span className="text-[10.5px]">{label}</span>
    </button>
  );
}

function DurationDetail({ job }: { job: JobItem }) {
  const { t } = useTranslation();
  const isRunning = job.status === "running" || job.status === "pending";
  const elapsed = useElapsedSeconds(job.created_at, isRunning);
  const dur = durationSeconds(job.created_at, job.finished_at);

  let text: string;
  if (isRunning) {
    text = t("record.elapsed", { time: formatDuration(elapsed) });
  } else if (dur != null) {
    text = formatDuration(dur);
  } else {
    return null;
  }

  return (
    <div className="mb-3">
      <div className="text-[10.5px] text-txt-3 uppercase tracking-[1px] mb-1">
        {t("preview.duration")}
      </div>
      <div className="text-[12px] text-txt-1 font-mono">⏱ {text}</div>
    </div>
  );
}

function Detail({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="mb-3">
      <div className="text-[10.5px] text-txt-3 uppercase tracking-[1px] mb-1">
        {label}
      </div>
      <div
        className={`text-[12px] text-txt-1 break-all ${mono ? "font-mono" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

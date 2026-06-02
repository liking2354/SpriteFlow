import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { JobItem } from "@/api/types";
import {
  durationSeconds,
  formatDuration,
  timeAgo,
  useElapsedSeconds,
} from "@/utils/time";

interface Props {
  job: JobItem;
  onPreview: (job: JobItem, index: number) => void;
  onUseAsRef: (img: { url: string; asset_id?: string; thumbnail?: string | null }) => void;
  onReuse: (job: JobItem) => void;        // 重新编辑：把参数填回左侧表单
  onRegenerate: (jobId: string) => void;  // 再次生成：直接克隆任务并入列
}

export function RecordCard({
  job,
  onPreview,
  onUseAsRef,
  onReuse,
  onRegenerate,
}: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [hoverImg, setHoverImg] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const setAssetFav = useMutation({
    mutationFn: ({ id, fav }: { id: string; fav: boolean }) =>
      api.setAssetFavorite(id, fav),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["assets-grid"] });
    },
  });

  const del = useMutation({
    mutationFn: () => api.deleteJob(job.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const copyPrompt = async () => {
    await navigator.clipboard.writeText(job.prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const download = (url: string, name: string) => {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.target = "_blank";
    a.rel = "noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const isRunning = job.status === "running" || job.status === "pending";
  const isFailed = job.status === "failed";
  const modeLabel = t(`generate.modes.${job.mode}`, { defaultValue: job.mode });
  const totalImagesCount = job.assets.length + (job.pending_children?.length || 0);

  // 父任务"正在生成"的实时秒表 / 已完成耗时
  const parentElapsed = useElapsedSeconds(job.created_at, isRunning);
  const parentDuration = durationSeconds(job.created_at, job.finished_at);

  return (
    <div className="group relative p-3 rounded-l border border-transparent hover:border-line hover:bg-bg-2/40 transition-colors">
      {/* 顶部：mode 徽章 + 时间 */}
      <div className="flex items-start gap-2.5 mb-2">
        <div
          className="w-9 h-9 rounded-s flex items-center justify-center text-[14px] flex-shrink-0"
          style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
        >
          {job.mode === "text2img" ? "✦" : job.mode === "img2img" ? "↻" : job.mode === "multi_fusion" ? "◇" : "▥"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[11.5px] font-medium text-txt-1">{modeLabel}</span>
            {job.params?.size && (
              <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-bg-3 text-txt-2">
                {job.params.size}
              </span>
            )}
            {totalImagesCount > 1 && (
              <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded bg-bg-3 text-txt-2">
                ×{totalImagesCount}
              </span>
            )}
            {parentDuration != null && !isRunning && (
              <span
                className="text-[9.5px] font-mono px-1.5 py-0.5 rounded"
                style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
                title={t("record.duration", { time: formatDuration(parentDuration) })}
              >
                ⏱ {formatDuration(parentDuration)}
              </span>
            )}
            <span className="ml-auto text-[10px] text-txt-3 font-mono">
              {timeAgo(job.created_at)}
            </span>
          </div>
        </div>
      </div>

      {/* prompt + 复制按钮（hover 显示） */}
      <div className="relative mb-2.5 group/p">
        <p className="text-[12.5px] text-txt-0 leading-relaxed line-clamp-3 pr-2">
          {job.prompt}
        </p>
        <button
          onClick={copyPrompt}
          className="absolute -top-1 right-0 opacity-0 group-hover/p:opacity-100 flex items-center gap-1 px-2.5 h-6 rounded-s border border-line bg-bg-2 text-[10.5px] text-txt-1 hover:text-txt-0 transition-opacity"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          {copied ? t("common.copied") : t("record.copyPrompt")}
        </button>
      </div>

      {/* 父任务自身正在生成（首次创建尚无任何输出）→ 大占位 */}
      {isRunning && job.assets.length === 0 && (
        <div
          className="relative mb-2.5 rounded-s overflow-hidden border border-[var(--acc)]/40 flex items-center justify-center"
          style={{
            height: 140,
            background:
              "radial-gradient(ellipse at center, var(--acc-soft) 0%, var(--bg-0) 70%)",
          }}
        >
          <div className="relative">
            <div
              className="w-12 h-12 rounded-full animate-pulse-glow"
              style={{
                background:
                  "conic-gradient(from 0deg, var(--acc), var(--cyan), var(--violet), var(--acc))",
                filter: "blur(2px)",
              }}
            />
            <div
              className="absolute inset-1.5 rounded-full"
              style={{ background: "var(--bg-1)" }}
            />
          </div>
          <div className="absolute bottom-3 left-0 right-0 text-center">
            <div className="text-[12px] text-txt-0 font-medium">
              {t("record.runningTitle")}
            </div>
            <div className="text-[10.5px] text-txt-2 mt-0.5 font-mono">
              ⏱ {t("record.elapsed", { time: formatDuration(parentElapsed) })}
            </div>
          </div>
        </div>
      )}

      {isFailed && (
        <div className="mb-2.5 px-2.5 py-2 rounded-s bg-[var(--red)]/10 border border-[var(--red)]/30 text-[11px] text-[var(--red)]">
          ⚠ {job.error || t("common.error")}
        </div>
      )}

      {/* 图片横向轨：已完成图 + 再次生成占位（横向滚动，固定高度） */}
      {(job.assets.length > 0 || (job.pending_children?.length || 0) > 0) && (
        <div
          className="flex gap-1.5 mb-2.5 overflow-x-auto pb-1 -mb-1"
          style={{ scrollbarWidth: "thin" }}
        >
          {job.assets.map((img, idx) => (
            <div
              key={img.id}
              className="relative group/i rounded-s overflow-hidden border border-line bg-bg-0 cursor-pointer flex-shrink-0"
              style={{ height: 104 }}
              onMouseEnter={() => setHoverImg(idx)}
              onMouseLeave={() => setHoverImg(null)}
              onClick={() => onPreview(job, idx)}
            >
              <img
                src={img.thumbnail || img.url}
                alt=""
                className="h-full w-auto block pixelated"
                style={{
                  aspectRatio:
                    img.width && img.height ? `${img.width}/${img.height}` : "1/1",
                }}
              />
              {/* hover 工具条 */}
              <div
                className={`absolute inset-0 transition-opacity ${
                  hoverImg === idx ? "opacity-100" : "opacity-0 pointer-events-none"
                }`}
                style={{
                  background:
                    "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.0) 40%, rgba(0,0,0,0.0) 60%, rgba(0,0,0,0.55) 100%)",
                }}
              >
                <div className="absolute top-1 right-1 flex gap-1">
                  <IconBtn
                    title={img.favorite ? t("record.unfavorite") : t("record.favorite")}
                    onClick={(e) => {
                      e.stopPropagation();
                      setAssetFav.mutate({ id: img.id, fav: !img.favorite });
                    }}
                    active={img.favorite}
                  >
                    {img.favorite ? "★" : "☆"}
                  </IconBtn>
                  <IconBtn
                    title={t("record.download")}
                    onClick={(e) => {
                      e.stopPropagation();
                      download(img.url, `${img.id}.png`);
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
                    </svg>
                  </IconBtn>
                </div>
                <div className="absolute bottom-1 left-1 flex gap-1">
                  <IconBtn
                    title={t("record.useAsRef")}
                    onClick={(e) => {
                      e.stopPropagation();
                      onUseAsRef({
                        url: img.url,
                        asset_id: img.id,
                        thumbnail: img.thumbnail,
                      });
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <circle cx="8.5" cy="8.5" r="1.5" />
                      <path d="m21 15-5-5L5 21" />
                    </svg>
                  </IconBtn>
                </div>
              </div>
            </div>
          ))}

          {/* 再次生成占位卡片 */}
          {(job.pending_children || []).map((c) => (
            <RegenPlaceholder key={c.job_id} child={c} />
          ))}
        </div>
      )}

      {/* 卡片底部操作 */}
      <div className="opacity-0 group-hover:opacity-100 flex gap-1.5 transition-opacity">
        {!isRunning && (
          <>
            <button
              onClick={() => onReuse(job)}
              className="flex items-center gap-1.5 px-2.5 h-7 rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[#2f3647]"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="m18.5 2.5 3 3L12 15l-4 1 1-4z" />
              </svg>
              {t("record.reuse")}
            </button>
            <button
              onClick={() => onRegenerate(job.id)}
              className="flex items-center gap-1.5 px-2.5 h-7 rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[#2f3647]"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" />
              </svg>
              {t("record.regenerate")}
            </button>
          </>
        )}
        <button
          onClick={() => del.mutate()}
          className="ml-auto flex items-center gap-1 px-2 h-7 rounded-s border border-line bg-bg-3 text-[11px] text-txt-2 hover:text-[var(--red)] hover:border-[var(--red)]/40"
          title={t("common.delete")}
        >
          🗑
        </button>
      </div>
    </div>
  );
}

function IconBtn({
  children,
  onClick,
  title,
  active,
}: {
  children: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  title?: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="w-7 h-7 grid place-items-center rounded-full bg-black/55 hover:bg-black/75 backdrop-blur-sm transition-colors text-white text-[12px]"
      style={active ? { color: "var(--amber)" } : undefined}
    >
      {children}
    </button>
  );
}

function RegenPlaceholder({
  child,
}: {
  child: { job_id: string; status: "pending" | "running" | "failed"; created_at: string };
}) {
  const { t } = useTranslation();
  const elapsed = useElapsedSeconds(child.created_at, child.status !== "failed");
  const failed = child.status === "failed";

  return (
    <div
      className="relative rounded-s overflow-hidden flex-shrink-0 flex items-center justify-center"
      style={{
        height: 104,
        width: 104,
        border: failed ? "1px solid rgba(255,91,110,0.4)" : "1px solid var(--acc-soft)",
        background: failed
          ? "rgba(255,91,110,0.06)"
          : "radial-gradient(ellipse at center, var(--acc-soft) 0%, var(--bg-0) 75%)",
      }}
    >
      {failed ? (
        <div className="text-center px-2">
          <div className="text-[14px] text-[var(--red)] mb-1">⚠</div>
          <div className="text-[10px] text-[var(--red)]">
            {t("record.regenFailed")}
          </div>
        </div>
      ) : (
        <>
          <div className="relative">
            <div
              className="w-9 h-9 rounded-full animate-pulse-glow"
              style={{
                background:
                  "conic-gradient(from 0deg, var(--acc), var(--cyan), var(--violet), var(--acc))",
                filter: "blur(1.5px)",
              }}
            />
            <div
              className="absolute inset-1 rounded-full"
              style={{ background: "var(--bg-1)" }}
            />
          </div>
          <div className="absolute bottom-1.5 left-0 right-0 text-center">
            <div className="text-[9px] text-txt-2 font-mono">
              ⏱ {formatDuration(elapsed)}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

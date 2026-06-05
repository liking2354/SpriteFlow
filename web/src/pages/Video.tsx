/**
 * /video — 视频生成页面
 *
 * 左：参数面板（mode + prompt + 素材选择 + 比例/分辨率/时长 + 高级）
 * 右：任务列表（状态过滤 + 卡片 + 操作）
 *
 * 视频任务异步：提交后由后端 worker 轮询完成；前端每 5s 拉一次列表，未结束任务展示状态徽章。
 * 24h URL 由后端在成功时立即下载入库，前端只见 asset；不直接依赖临时 URL。
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  AssetItem,
  VideoCreateInput,
  VideoMode,
  VideoStatus,
  VideoTaskItem,
} from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextArea, TextInput, Switch } from "@/components/ui/Field";
import { Segment } from "@/components/ui/Segment";
import { AssetPicker } from "@/components/ui/AssetPicker";
import { useConfirm } from "@/components/ui/Confirm";

type Filter = "all" | "active" | "done" | "failed";

const SETTLED: VideoStatus[] = ["succeeded", "failed", "cancelled", "expired"];

export function VideoPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const confirm = useConfirm();

  // ----- 表单 -----
  const [mode, setMode] = useState<VideoMode>("text2video");
  const [prompt, setPrompt] = useState("");
  const [firstFrame, setFirstFrame] = useState<AssetItem | null>(null);
  const [lastFrame, setLastFrame] = useState<AssetItem | null>(null);
  const [refs, setRefs] = useState<AssetItem[]>([]);
  const [pickerFor, setPickerFor] = useState<null | "first" | "last" | "ref">(null);

  const [ratio, setRatio] = useState("16:9");
  const [resolution, setResolution] = useState<"480p" | "720p" | "1080p">("720p");
  const [duration, setDuration] = useState(5);
  const [seed, setSeed] = useState("");
  const [camerafixed, setCamerafixed] = useState(false);
  const [watermark, setWatermark] = useState(false);
  const [returnLastFrame, setReturnLastFrame] = useState(false);
  const [generateAudio, setGenerateAudio] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  /** 自定义模型 ID（留空走后端默认 SEEDANCE_MODEL） */
  const [modelOverride, setModelOverride] = useState("");

  const [filter, setFilter] = useState<Filter>("all");
  const [detail, setDetail] = useState<VideoTaskItem | null>(null);

  // ----- 任务列表 -----
  const tasksQuery = useQuery({
    queryKey: ["video-tasks", filter],
    queryFn: () => {
      const status: VideoStatus | "all" =
        filter === "active"
          ? "running"
          : filter === "done"
          ? "succeeded"
          : filter === "failed"
          ? "failed"
          : "all";
      return api.listVideoTasks({
        status: status === "all" ? undefined : status,
        limit: 50,
      });
    },
    refetchInterval: (q) => {
      const data = q.state.data as { items?: VideoTaskItem[] } | undefined;
      const items = data?.items || [];
      const hasActive = items.some((it) => !SETTLED.includes(it.status));
      return hasActive ? 5000 : false;
    },
  });

  const items = tasksQuery.data?.items || [];

  // ----- 校验 + 提交 -----
  const validate = (): string | null => {
    if (mode === "text2video" && !prompt.trim()) return t("video.needPrompt");
    if (mode === "image2video_first" && !firstFrame) return t("video.needFirstFrame");
    if (mode === "first_last" && !(firstFrame && lastFrame)) return t("video.needFirstAndLast");
    if (mode === "multi_ref" && refs.length === 0) return t("video.needAtLeastOneRef");
    return null;
  };

  const buildPayload = (): VideoCreateInput => ({
    mode,
    prompt: prompt.trim(),
    first_frame_asset_id: firstFrame?.id || null,
    last_frame_asset_id: lastFrame?.id || null,
    ref_asset_ids: refs.map((r) => r.id),
    model: modelOverride.trim() || null,
    ratio,
    resolution,
    duration,
    seed: seed === "" ? null : Number(seed),
    camerafixed,
    watermark,
    return_last_frame: returnLastFrame,
    generate_audio: generateAudio,
  });

  const createMut = useMutation({
    mutationFn: (req: VideoCreateInput) => api.createVideoTask(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["video-tasks"] });
    },
  });

  const onSubmit = () => {
    const err = validate();
    if (err) {
      alert(err);
      return;
    }
    createMut.mutate(buildPayload());
  };

  // ----- 任务操作 -----
  const cancelMut = useMutation({
    mutationFn: (id: string) => api.cancelVideoTask(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video-tasks"] }),
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteVideoTask(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video-tasks"] }),
  });

  const onCancel = async (it: VideoTaskItem) => {
    const ok = await confirm({
      title: t("video.confirmCancelTitle"),
      message: t("video.confirmCancelHint"),
      variant: "danger",
    });
    if (ok) cancelMut.mutate(it.id);
  };
  const onDelete = async (it: VideoTaskItem) => {
    const ok = await confirm({
      title: t("video.confirmDeleteTitle"),
      message: t("video.confirmDeleteHint"),
      variant: "danger",
    });
    if (ok) deleteMut.mutate(it.id);
  };

  // 抽屉同步
  useEffect(() => {
    if (!detail) return;
    const fresh = items.find((i) => i.id === detail.id);
    if (fresh && fresh.updated_at !== detail.updated_at) setDetail(fresh);
  }, [items, detail]);

  // ----- 渲染 -----
  return (
    <div
      className="grid gap-5 max-w-[1500px] items-start"
      style={{ gridTemplateColumns: "minmax(380px, 440px) 1fr" }}
    >
      {/* 左：参数面板 */}
      <div className="space-y-4">
        <Card title={t("video.title")} subtitle={t("video.subtitle")}>
          <Field label={t("video.mode")}>
            <Segment
              items={[
                { value: "text2video", label: t("video.modeText2Video") },
                { value: "image2video_first", label: t("video.modeImage2VideoFirst") },
                { value: "first_last", label: t("video.modeFirstLast") },
                { value: "multi_ref", label: t("video.modeMultiRef") },
              ]}
              value={mode}
              onChange={(v) => setMode(v as VideoMode)}
            />
          </Field>

          <Field label={t("video.prompt")}>
            <TextArea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t("video.promptPlaceholder") as string}
            />
          </Field>

          {/* 素材选择按 mode 切换 */}
          {mode === "image2video_first" && (
            <Field label={t("video.firstFrame")}>
              <FrameSlot
                asset={firstFrame}
                onPick={() => setPickerFor("first")}
                onClear={() => setFirstFrame(null)}
              />
            </Field>
          )}
          {mode === "first_last" && (
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("video.firstFrame")}>
                <FrameSlot
                  asset={firstFrame}
                  onPick={() => setPickerFor("first")}
                  onClear={() => setFirstFrame(null)}
                />
              </Field>
              <Field label={t("video.lastFrame")}>
                <FrameSlot
                  asset={lastFrame}
                  onPick={() => setPickerFor("last")}
                  onClear={() => setLastFrame(null)}
                />
              </Field>
            </div>
          )}
          {mode === "multi_ref" && (
            <Field label={t("video.refImages")} hint={t("video.tipNoRealFace")}>
              <RefStrip
                assets={refs}
                onAdd={() => setPickerFor("ref")}
                onRemove={(id) => setRefs(refs.filter((r) => r.id !== id))}
                max={9}
              />
            </Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label={t("video.ratio")}>
              <Segment
                items={[
                  { value: "16:9", label: "16:9" },
                  { value: "9:16", label: "9:16" },
                  { value: "1:1", label: "1:1" },
                  { value: "4:3", label: "4:3" },
                  { value: "3:4", label: "3:4" },
                  { value: "21:9", label: "21:9" },
                  { value: "adaptive", label: t("video.ratioAdaptive") },
                ]}
                value={ratio}
                onChange={setRatio}
              />
            </Field>
            <Field label={t("video.resolution")}>
              <Segment
                items={[
                  { value: "480p", label: "480p" },
                  { value: "720p", label: "720p" },
                  { value: "1080p", label: "1080p" },
                ]}
                value={resolution}
                onChange={(v) => setResolution(v as "480p" | "720p" | "1080p")}
              />
            </Field>
          </div>

          <Field label={`${t("video.duration")}: ${duration}s`}>
            <input
              type="range"
              min={4}
              max={15}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full accent-[var(--acc)]"
            />
          </Field>

          {/* 高级 */}
          <button
            onClick={() => setAdvanced((a) => !a)}
            className="text-[11px] text-txt-3 hover:text-txt-1 mt-1"
          >
            {advanced ? "▾" : "▸"} {t("video.advanced")}
          </button>
          {advanced && (
            <div className="space-y-3 mt-2 pt-3 border-t border-line">
              <Field label={t("video.model")} hint="留空走后端 .env 的 SEEDANCE_MODEL；选择预设或填自定义模型 ID 可临时覆盖">
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {[
                    { id: "", label: "默认" },
                    { id: "doubao-seedance-1-5-pro-251215", label: "1.5 Pro" },
                    { id: "doubao-seedance-2-0-260128", label: "2.0" },
                    { id: "doubao-seedance-2-0-fast-260128", label: "2.0 Fast" },
                  ].map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setModelOverride(m.id)}
                      className={`h-7 px-2.5 rounded-s border text-[11px] transition-colors ${
                        modelOverride === m.id
                          ? "border-[var(--acc)] bg-[var(--acc)]/15 text-txt-0"
                          : "border-line bg-bg-3 text-txt-2 hover:text-txt-0 hover:border-[var(--acc)]/60"
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                <TextInput
                  type="text"
                  value={modelOverride}
                  onChange={(e) => setModelOverride(e.target.value)}
                  placeholder="doubao-seedance-... (自定义模型 ID)"
                />
              </Field>
              <Field label={t("video.seed")} hint={t("video.seedHint")}>
                <TextInput
                  type="text"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder="-1"
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Switch checked={camerafixed} onChange={setCamerafixed} label={t("video.camerafixed")} />
                <Switch checked={watermark} onChange={setWatermark} label={t("video.watermark")} />
                <Switch checked={returnLastFrame} onChange={setReturnLastFrame} label={t("video.returnLastFrame")} />
                <Switch checked={generateAudio} onChange={setGenerateAudio} label={t("video.generateAudio")} />
              </div>
            </div>
          )}

          <Button
            variant="primary"
            className="w-full mt-3"
            loading={createMut.isPending}
            onClick={onSubmit}
          >
            🎬 {createMut.isPending ? t("video.submitting") : t("video.submit")}
          </Button>

          {createMut.isError && (
            <div className="mt-2 px-3 py-2 bg-[var(--red)]/10 border border-[var(--red)]/30 rounded-s text-[11.5px] text-[var(--red)]">
              ⚠ {String(createMut.error)}
            </div>
          )}
          <div className="mt-3 text-[10.5px] text-txt-3 leading-relaxed">
            💡 {t("video.tipGifQuality")}
          </div>
        </Card>
      </div>

      {/* 右：任务列表 + 详情 */}
      <Card
        title={t("video.tasks")}
        actions={
          <Segment
            items={[
              { value: "all", label: t("video.filterAll") },
              { value: "active", label: t("video.filterActive") },
              { value: "done", label: t("video.filterDone") },
              { value: "failed", label: t("video.filterFailed") },
            ]}
            value={filter}
            onChange={(v) => setFilter(v as Filter)}
          />
        }
      >
        {items.length === 0 ? (
          <div className="text-center py-20 text-txt-3 text-[12px]">
            {t("video.noTasks")}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {items.map((it) => (
              <TaskCard
                key={it.id}
                item={it}
                onPlay={() => setDetail(it)}
                onCancel={() => onCancel(it)}
                onDelete={() => onDelete(it)}
                onReuse={() => {
                  setMode(it.mode);
                  setPrompt(it.prompt);
                  setRatio((it.params as any).ratio || "16:9");
                  setResolution(((it.params as any).resolution as any) || "720p");
                  setDuration((it.params as any).duration || 5);
                }}
              />
            ))}
          </div>
        )}
      </Card>

      {/* 素材选择器 */}
      <AssetPicker
        open={pickerFor !== null}
        onClose={() => setPickerFor(null)}
        onPick={(a) => {
          if (pickerFor === "first") setFirstFrame(a);
          else if (pickerFor === "last") setLastFrame(a);
          else if (pickerFor === "ref" && refs.length < 9) setRefs([...refs, a]);
          setPickerFor(null);
        }}
      />

      {/* 详情抽屉 */}
      {detail && (
        <DetailDrawer
          item={detail}
          onClose={() => setDetail(null)}
          onCancel={() => onCancel(detail)}
          onDelete={() => onDelete(detail)}
        />
      )}
    </div>
  );
}

// ============================ 子组件 ============================

function FrameSlot({
  asset,
  onPick,
  onClear,
}: {
  asset: AssetItem | null;
  onPick: () => void;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  if (!asset) {
    return (
      <button
        onClick={onPick}
        className="aspect-video w-full rounded-l border-2 border-dashed border-line hover:border-[var(--acc)] hover:bg-[var(--acc-soft)]/40 grid place-items-center text-[12px] text-txt-3"
      >
        ⊞ {t("video.pickImage")}
      </button>
    );
  }
  return (
    <div className="relative rounded-l border border-line overflow-hidden bg-bg-0">
      <img
        src={asset.thumbnail || asset.uri}
        alt=""
        className="w-full max-h-[160px] object-contain"
      />
      <button
        onClick={onClear}
        className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 text-white text-[12px] grid place-items-center hover:bg-[var(--red)]"
      >
        ✕
      </button>
    </div>
  );
}

function RefStrip({
  assets,
  onAdd,
  onRemove,
  max,
}: {
  assets: AssetItem[];
  onAdd: () => void;
  onRemove: (id: string) => void;
  max: number;
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {assets.map((a) => (
        <div key={a.id} className="relative aspect-square rounded-s border border-line overflow-hidden bg-bg-0">
          <img
            src={a.thumbnail || a.uri}
            alt=""
            className="w-full h-full object-cover"
          />
          <button
            onClick={() => onRemove(a.id)}
            className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/65 text-white text-[10px] grid place-items-center hover:bg-[var(--red)]"
          >
            ✕
          </button>
        </div>
      ))}
      {assets.length < max && (
        <button
          onClick={onAdd}
          className="aspect-square rounded-s border-2 border-dashed border-line hover:border-[var(--acc)] grid place-items-center text-[18px] text-txt-3 hover:text-[var(--acc)]"
        >
          +
        </button>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: VideoStatus }) {
  const { t } = useTranslation();
  const map: Record<VideoStatus, { color: string; bg: string }> = {
    queued: { color: "var(--txt-2)", bg: "var(--bg-3)" },
    running: { color: "var(--acc)", bg: "var(--acc-soft)" },
    succeeded: { color: "var(--green)", bg: "rgba(34,197,94,0.12)" },
    failed: { color: "var(--red)", bg: "rgba(239,68,68,0.12)" },
    cancelled: { color: "var(--txt-3)", bg: "var(--bg-3)" },
    expired: { color: "var(--txt-3)", bg: "var(--bg-3)" },
  };
  const s = map[status];
  return (
    <span
      className="inline-flex items-center px-2 h-5 rounded-full text-[10px] font-medium"
      style={{ color: s.color, background: s.bg }}
    >
      {t(`video.stat.${status}`)}
    </span>
  );
}

function TaskCard({
  item,
  onPlay,
  onCancel,
  onDelete,
  onReuse,
}: {
  item: VideoTaskItem;
  onPlay: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onReuse: () => void;
}) {
  const { t } = useTranslation();
  const cover = useMemo(() => {
    if (item.result_asset?.thumbnail) return item.result_asset.thumbnail;
    if (item.result_asset?.uri) return item.result_asset.uri;
    return null;
  }, [item.result_asset]);

  return (
    <div className="relative rounded-l border border-line bg-bg-2 overflow-hidden hover:border-[var(--acc)]/60 transition-colors">
      <div
        className="aspect-video grid place-items-center cursor-pointer relative"
        style={{
          background:
            "repeating-conic-gradient(#1c2230 0% 25%, #161b24 0% 50%) 50% / 24px 24px",
        }}
        onClick={onPlay}
      >
        {item.status === "succeeded" && item.result_asset ? (
          <video
            src={item.result_asset.uri}
            poster={cover || undefined}
            muted
            loop
            playsInline
            preload="metadata"
            className="w-full h-full object-contain"
            onMouseEnter={(e) => (e.currentTarget as HTMLVideoElement).play().catch(() => {})}
            onMouseLeave={(e) => {
              const v = e.currentTarget as HTMLVideoElement;
              v.pause();
              v.currentTime = 0;
            }}
          />
        ) : item.status === "running" || item.status === "queued" ? (
          <div className="text-center text-[11px] text-txt-3">
            <div className="inline-block w-6 h-6 border-2 border-[var(--acc)] border-t-transparent rounded-full animate-spin mb-1" />
            <div>{t(`video.stat.${item.status}`)}</div>
          </div>
        ) : (
          <div className="text-[11px] text-txt-3 px-3 text-center">
            {item.error || t(`video.stat.${item.status}`)}
          </div>
        )}
        <span className="absolute top-1.5 left-1.5">
          <StatusPill status={item.status} />
        </span>
      </div>
      <div className="p-2.5 space-y-1.5">
        <div className="text-[11.5px] text-txt-1 line-clamp-2 min-h-[32px]">
          {item.prompt || <span className="text-txt-3">—</span>}
        </div>
        <div className="text-[10px] text-txt-3 font-mono flex items-center gap-2">
          <span>{item.mode}</span>
          <span>·</span>
          <span>{(item.params as any).resolution || "720p"}</span>
          <span>·</span>
          <span>{(item.params as any).duration || 5}s</span>
        </div>
        <div className="flex items-center gap-1 pt-1">
          {item.status === "succeeded" && item.result_asset && (
            <a
              href={item.result_asset.uri}
              target="_blank"
              rel="noreferrer"
              className="flex-1 h-7 grid place-items-center rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
              download
            >
              ⬇ {t("video.downloadVideo")}
            </a>
          )}
          <button
            onClick={onReuse}
            title={t("video.regenerate")}
            className="flex-1 h-7 grid place-items-center rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
          >
            ⟳
          </button>
          {item.status === "queued" ? (
            <button
              onClick={onCancel}
              title={t("video.cancel")}
              className="h-7 px-2 rounded-s border border-line bg-bg-3 text-[11px] text-txt-2 hover:text-[var(--red)] hover:border-[var(--red)]/60"
            >
              ⏹
            </button>
          ) : (
            <button
              onClick={onDelete}
              title={t("video.delete")}
              className="h-7 px-2 rounded-s border border-[var(--red)]/40 bg-bg-3 text-[11px] text-[var(--red)] hover:bg-[var(--red)]/10"
            >
              🗑
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailDrawer({
  item,
  onClose,
  onCancel,
  onDelete,
}: {
  item: VideoTaskItem;
  onClose: () => void;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="fixed inset-0 z-[100] flex items-stretch justify-end"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[640px] h-full overflow-y-auto bg-bg-1 border-l border-line p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[14px] font-semibold text-txt-0 mb-1">
              {item.prompt || "—"}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-txt-3">
              <StatusPill status={item.status} />
              <span className="font-mono">{item.mode}</span>
              <span>·</span>
              <span className="font-mono">{item.created_at.replace("T", " ").slice(0, 19)}</span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 grid place-items-center rounded-full border border-line hover:bg-bg-3"
          >
            ✕
          </button>
        </div>

        {/* 输出视频 */}
        <div
          className="rounded-l border border-line overflow-hidden"
          style={{ background: "repeating-conic-gradient(#1c2230 0% 25%, #161b24 0% 50%) 50% / 24px 24px" }}
        >
          {item.status === "succeeded" && item.result_asset ? (
            <video
              src={item.result_asset.uri}
              poster={item.result_asset.thumbnail || undefined}
              controls
              className="w-full max-h-[60vh] bg-black"
            />
          ) : (
            <div className="aspect-video grid place-items-center text-[12px] text-txt-3 px-3 text-center">
              {item.error || t(`video.stat.${item.status}`)}
            </div>
          )}
        </div>

        {/* 操作 */}
        <div className="flex items-center gap-2">
          {item.result_asset && (
            <a
              href={item.result_asset.uri}
              target="_blank"
              rel="noreferrer"
              download
              className="px-3 h-8 grid place-items-center rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
            >
              ⬇ {t("video.downloadVideo")}
            </a>
          )}
          <button
            onClick={() => {
              if (item.prompt) navigator.clipboard?.writeText(item.prompt).catch(() => {});
            }}
            className="px-3 h-8 grid place-items-center rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
          >
            ⎘ {t("video.copyPrompt")}
          </button>
          <span className="ml-auto" />
          {item.status === "queued" && (
            <button
              onClick={onCancel}
              className="px-3 h-8 rounded-s border border-line bg-bg-3 text-[12px] text-txt-2 hover:text-[var(--red)] hover:border-[var(--red)]/60"
            >
              ⏹ {t("video.cancel")}
            </button>
          )}
          <button
            onClick={onDelete}
            className="px-3 h-8 rounded-s border border-[var(--red)]/40 bg-bg-3 text-[12px] text-[var(--red)] hover:bg-[var(--red)]/10"
          >
            🗑 {t("video.delete")}
          </button>
        </div>

        {/* 参数 */}
        <div>
          <div className="text-[11.5px] text-txt-2 mb-2">{t("video.fields.params")}</div>
          <pre className="text-[10.5px] text-txt-3 font-mono bg-bg-3 rounded-s border border-line p-3 overflow-auto whitespace-pre-wrap">
{JSON.stringify({ model: item.model, ...item.params }, null, 2)}
          </pre>
        </div>

        {/* 输入素材（如果有） */}
        {(item.inputs.first_frame_asset_id ||
          item.inputs.last_frame_asset_id ||
          (item.inputs.ref_asset_ids && item.inputs.ref_asset_ids.length > 0)) && (
          <div>
            <div className="text-[11.5px] text-txt-2 mb-2">{t("video.fields.input")}</div>
            <div className="text-[10.5px] text-txt-3 font-mono space-y-1">
              {item.inputs.first_frame_asset_id && (
                <div>first_frame: {item.inputs.first_frame_asset_id}</div>
              )}
              {item.inputs.last_frame_asset_id && (
                <div>last_frame: {item.inputs.last_frame_asset_id}</div>
              )}
              {item.inputs.ref_asset_ids?.map((id) => (
                <div key={id}>ref: {id}</div>
              ))}
            </div>
          </div>
        )}

        {/* 尾帧 */}
        {item.last_frame_asset && (
          <div>
            <div className="text-[11.5px] text-txt-2 mb-2">{t("video.fields.lastFrameOut")}</div>
            <img
              src={item.last_frame_asset.thumbnail || item.last_frame_asset.uri}
              alt=""
              className="rounded-s border border-line max-h-[200px]"
            />
          </div>
        )}

        {item.usage_tokens != null && (
          <div className="text-[11px] text-txt-3 font-mono">
            {t("video.fields.tokens")}: {item.usage_tokens}
          </div>
        )}

        {item.error && (
          <div className="px-3 py-2 bg-[var(--red)]/10 border border-[var(--red)]/30 rounded-s text-[11.5px] text-[var(--red)]">
            ⚠ {item.error}
          </div>
        )}
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { FiSettings, FiZap, FiRepeat } from "react-icons/fi";
import { FaStar, FaRegStar } from "react-icons/fa6";
import { api, subscribeGenerateStream } from "@/api/client";
import type { GenerateMode, GenerateRequest, JobItem } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextArea, TextInput, Switch } from "@/components/ui/Field";
import { Segment } from "@/components/ui/Segment";
import { SizePopover } from "@/components/ui/SizePopover";
import { CountSlider } from "@/components/ui/CountSlider";
import {
  RefImagePicker,
  type RefImage,
} from "@/components/ui/RefImagePicker";
import { RecordCard } from "@/components/RecordCard";
import { ImagePreview } from "@/components/ImagePreview";
import { useConfirm } from "@/components/ui/Confirm";

type Tab = "creations" | "myAssets" | "myFavorites";

export function GeneratePage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const confirm = useConfirm();

  // ---------- 表单状态 ----------
  const [mode, setMode] = useState<GenerateMode>("text2img");
  const [prompt, setPrompt] = useState("");
  const [refs, setRefs] = useState<RefImage[]>([]);
  const [resolution, setResolution] = useState<"2k" | "4k">("2k");
  const [ratio, setRatio] = useState<string>("1:1");
  const [width, setWidth] = useState(2048);
  const [height, setHeight] = useState(2048);
  const [seed, setSeed] = useState<string>("");
  const [maxImages, setMaxImages] = useState(3);
  const [watermark, setWatermark] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [saveAsset, setSaveAsset] = useState(true);
  const [tags, setTags] = useState("");

  // ---------- 右侧 Tab + 预览 ----------
  const [tab, setTab] = useState<Tab>("creations");
  const [preview, setPreview] = useState<{ job: JobItem; index: number } | null>(null);

  // ---------- 创作记录列表 ----------
  const jobsQuery = useQuery({
    queryKey: ["jobs", tab],
    queryFn: () =>
      api.listJobs({
        favorite: tab === "myFavorites" ? true : undefined,
        limit: 30,
      }),
    refetchInterval: (q) => {
      // 父任务 running 或有 pending children 时 2s 轮询
      const data = q.state.data as any;
      const items: JobItem[] = data?.items || [];
      const hasActive = items.some(
        (j) =>
          j.status === "running" ||
          j.status === "pending" ||
          (j.pending_children && j.pending_children.length > 0)
      );
      return hasActive ? 2000 : false;
    },
  });

  // ---------- 表单参数构建 ----------
  const buildRequest = (): GenerateRequest => ({
    mode,
    prompt: prompt.trim(),
    image_urls: refs.filter((r) => r.origin === "url").map((r) => r.url),
    ref_asset_ids: refs.filter((r) => r.asset_id).map((r) => r.asset_id!) as string[],
    width,
    height,
    seed: seed ? Number(seed) : null,
    max_images: maxImages,
    watermark,
    web_search: webSearch,
    save_as_asset: saveAsset,
    tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
  });

  const validate = (): string | null => {
    if (!prompt.trim()) return t("generate.errors.promptRequired");
    if (mode === "img2img" && refs.length === 0)
      return t("generate.errors.imagesRequired", { mode: "img2img" });
    if (mode === "multi_fusion" && refs.length < 2)
      return t("generate.errors.imagesFusionMin");
    if (width * height < 3_686_400) return t("generate.errors.sizeTooSmall");
    return null;
  };

  // ---------- mutation ----------
  const generate = useMutation({
    mutationFn: api.generate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const regenerate = useMutation({
    mutationFn: (id: string) => api.regenerateJob(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const [streaming, setStreaming] = useState<string | null>(null);

  const handleGenerate = async () => {
    const err = validate();
    if (err) {
      await confirm({
        title: t("common.error"),
        message: err,
        okText: t("common.confirm"),
        cancelText: " ",
      });
      return;
    }
    // 异步：后端立即返回 job_id，无需等待，列表轮询会自动显示进度
    generate.mutate(buildRequest(), {
      onSuccess: () => {
        // 立刻插入 loading 卡片到列表
        queryClient.invalidateQueries({ queryKey: ["jobs"] });
      },
    });
  };

  const handleStream = async () => {
    const err = validate();
    if (err) {
      await confirm({
        title: t("common.error"),
        message: err,
        okText: t("common.confirm"),
        cancelText: " ",
      });
      return;
    }
    try {
      const { run_id } = await api.startStream({ ...buildRequest(), mode: "sequential" });
      setStreaming(run_id);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      const close = subscribeGenerateStream(
        run_id,
        () => {
          // 任何事件来都刷新列表（让卡片实时显示输出）
          queryClient.invalidateQueries({ queryKey: ["jobs"] });
        },
        () => setStreaming(null)
      );
      const stop = () => {
        setStreaming(null);
        close();
      };
      // 完成后停
      const checker = setInterval(async () => {
        try {
          const j = await api.getJob(run_id);
          if (j.status === "completed" || j.status === "failed") {
            clearInterval(checker);
            stop();
          }
        } catch {
          /* ignore */
        }
      }, 2500);
    } catch (e) {
      setStreaming(null);
      await confirm({
        title: t("common.error"),
        message: String(e),
        okText: t("common.confirm"),
        cancelText: " ",
        variant: "danger",
      });
    }
  };

  // ---------- 一键清空 ----------
  const hasInputs =
    !!prompt ||
    refs.length > 0 ||
    !!seed ||
    !!tags ||
    watermark ||
    webSearch;

  const clearAll = async () => {
    if (hasInputs) {
      const ok = await confirm({
        title: t("generate.actions.clear"),
        message: t("generate.actions.clearConfirm"),
        variant: "danger",
      });
      if (!ok) return;
    }
    setPrompt("");
    setRefs([]);
    setSeed("");
    setTags("");
    setWatermark(false);
    setWebSearch(false);
    setSaveAsset(true);
    setMaxImages(3);
    setRatio("1:1");
    setResolution("2k");
    setWidth(2048);
    setHeight(2048);
  };

  // ---------- 当 mode 改变时清理参考图 ----------
  useEffect(() => {
    if (mode === "text2img" && refs.length > 0) setRefs([]);
  }, [mode]);

  // ---------- 复用 / 用作参考图 ----------
  const useAsRef = (img: { url: string; asset_id?: string; thumbnail?: string | null }) => {
    if (mode === "text2img") setMode("img2img");
    setRefs((prev) => {
      const max = mode === "multi_fusion" ? 8 : mode === "img2img" ? 1 : 4;
      const next: RefImage = {
        url: img.url,
        thumbnail: img.thumbnail,
        asset_id: img.asset_id,
        origin: img.asset_id ? "asset" : "url",
      };
      const list = [...prev.slice(-(max - 1)), next];
      return list;
    });
  };

  const reuse = (job: JobItem) => {
    setMode(job.mode);
    setPrompt(job.prompt);
    if (job.params?.width && job.params?.height) {
      setWidth(job.params.width as number);
      setHeight(job.params.height as number);
      setRatio("custom");
    }
    if (typeof job.params?.max_images === "number") setMaxImages(job.params.max_images);
    if (job.params?.seed != null) setSeed(String(job.params.seed));
    setWatermark(!!job.params?.watermark);
    setWebSearch(!!job.params?.web_search);
    if (job.params?.tags) setTags((job.params.tags as string[]).join(","));
    // 还原参考图：直接用后端附带的 ref_assets（已含预签名 URL）
    const next: RefImage[] = (job.ref_assets || []).map((r) => ({
      url: r.url,
      thumbnail: r.thumbnail || r.url,
      asset_id: r.asset_id || undefined,
      origin: r.origin === "asset" ? "asset" : "url",
    }));
    setRefs(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ---------- 参考图最大数 ----------
  const refMax =
    mode === "img2img" ? 1 : mode === "multi_fusion" ? 8 : mode === "sequential" ? 4 : 0;

  const items = jobsQuery.data?.items || [];
  const filtered = useMemo(() => items, [items]);

  return (
    <div className="grid gap-5 max-w-[1500px]" style={{ gridTemplateColumns: "minmax(420px, 480px) 1fr" }}>
      {/* ====================== 左侧：输入区 ====================== */}
      <div className="space-y-4">
        <Card
          title={t("generate.title")}
          subtitle={t("generate.subtitle")}
          actions={
            <button
              type="button"
              onClick={clearAll}
              disabled={!hasInputs}
              title={t("generate.actions.clear")}
              className="flex items-center gap-1.5 px-2.5 h-7 rounded-s border border-line bg-bg-3 text-[11px] text-txt-2 hover:text-txt-0 hover:border-[#2f3647] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6M14 11v6" />
              </svg>
              {t("generate.actions.clear")}
            </button>
          }
        >
          {/* 模式 */}
          <Field>
            <Segment
              items={[
                { value: "text2img", label: t("generate.modes.text2img") },
                { value: "img2img", label: t("generate.modes.img2img") },
                { value: "multi_fusion", label: t("generate.modes.multi_fusion") },
                { value: "sequential", label: t("generate.modes.sequential") },
              ]}
              value={mode}
              onChange={(v) => setMode(v as GenerateMode)}
            />
            <div className="mt-2 text-[11px] text-txt-2">
              {t(`generate.modeDesc.${mode}`)}
            </div>
          </Field>

          {/* 参考图 */}
          {refMax > 0 && (
            <Field label={t("generate.fields.imageUrls")}>
              <RefImagePicker values={refs} max={refMax} onChange={setRefs} />
            </Field>
          )}

          {/* 提示词 */}
          <Field label={t("generate.fields.prompt")}>
            <TextArea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t("generate.fields.promptPlaceholder")}
            />
          </Field>

          {/* 触发按钮组：尺寸 + 数量 */}
          <div className="flex items-center gap-2 flex-wrap mb-4">
            <SizePopover
              resolution={resolution}
              ratio={ratio}
              width={width}
              height={height}
              onChange={({ resolution, ratio, width, height }) => {
                setResolution(resolution);
                setRatio(ratio);
                setWidth(width);
                setHeight(height);
              }}
            />
            {mode === "sequential" && (
              <CountSlider value={maxImages} onChange={setMaxImages} max={15} />
            )}
            <div className="ml-auto text-[10.5px] text-txt-3 font-mono">
              {width}×{height}
            </div>
          </div>

          {/* 高级 */}
          <details className="mb-4">
            <summary className="text-[11px] text-txt-2 cursor-pointer hover:text-txt-0 select-none mb-2">
              <FiSettings size={14} className="inline" /> 高级选项
            </summary>
            <div className="grid grid-cols-2 gap-3 mt-2">
              <Field label={t("generate.fields.seed")}>
                <TextInput
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder={t("generate.fields.seedPlaceholder")}
                />
              </Field>
              <Field label={t("generate.fields.tags")}>
                <TextInput
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder={t("generate.fields.tagsPlaceholder")}
                />
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-3 mt-1">
              <Switch
                checked={saveAsset}
                onChange={setSaveAsset}
                label={t("generate.fields.saveAsAsset")}
              />
              <Switch
                checked={watermark}
                onChange={setWatermark}
                label={t("generate.fields.watermark")}
              />
              <Switch
                checked={webSearch}
                onChange={setWebSearch}
                label={t("generate.fields.webSearch")}
              />
            </div>
          </details>

          {/* 操作按钮 */}
          <div className="flex gap-2.5">
            <Button
              variant="primary"
              loading={generate.isPending}
              onClick={handleGenerate}
              disabled={!!streaming}
              className="flex-1"
            >
              {generate.isPending ? t("generate.actions.generating") : t("generate.actions.generate")}
            </Button>
            {mode === "sequential" && (
              <Button
                variant="outline"
                loading={!!streaming}
                onClick={handleStream}
                disabled={generate.isPending}
              >
                <FiZap size={14} /> {t("generate.actions.stream")}
              </Button>
            )}
          </div>

          {generate.error && (
            <div className="mt-3 px-3 py-2 bg-[var(--red)]/10 border border-[var(--red)]/30 rounded-s text-[12px] text-[var(--red)]">
              {String(generate.error)}
            </div>
          )}
        </Card>
      </div>

      {/* ====================== 右侧：创作记录 ====================== */}
      <Card
        title={
          <Segment
            className="!w-[360px]"
            items={[
              { value: "creations", label: t("tabs.creations") },
              { value: "myAssets", label: t("tabs.myAssets") },
              { value: "myFavorites", label: t("tabs.myFavorites") },
            ]}
            value={tab}
            onChange={setTab}
          />
        }
        actions={
          <Button size="sm" variant="ghost" onClick={() => jobsQuery.refetch()}>
            ⟳
          </Button>
        }
      >
        {tab === "creations" ? (
          <div
            className="flex flex-col overflow-y-auto pr-1 -mr-1"
            style={{ maxHeight: "calc(100vh - 240px)" }}
          >
            {jobsQuery.isLoading && (
              <div className="text-center py-12 text-txt-3 text-[12px]">
                {t("common.loading")}
              </div>
            )}
            {!jobsQuery.isLoading && filtered.length === 0 && (
              <div className="text-center py-16 text-txt-3 text-[12px]">
                {t("generate.creationsEmpty")}
              </div>
            )}
            {filtered.map((job) => (
              <RecordCard
                key={job.id}
                job={job}
                onPreview={(j, i) => setPreview({ job: j, index: i })}
                onUseAsRef={useAsRef}
                onReuse={reuse}
                onRegenerate={(id) => regenerate.mutate(id)}
              />
            ))}
          </div>
        ) : (
          <div
            className="overflow-y-auto pr-1 -mr-1"
            style={{ maxHeight: "calc(100vh - 240px)" }}
          >
            <AssetGridTab
              onUseAsRef={useAsRef}
              favoriteOnly={tab === "myFavorites"}
            />
          </div>
        )}
      </Card>

      {/* 大图预览 */}
      {preview && (
        <ImagePreview
          job={preview.job}
          initialIndex={preview.index}
          onClose={() => setPreview(null)}
          onUseAsRef={useAsRef}
          onReuse={reuse}
          onRegenerate={(id) => regenerate.mutate(id)}
        />
      )}
    </div>
  );
}

// ============== 素材网格 Tab（我的资产 / 我的收藏 共用） ==============

function AssetGridTab({
  onUseAsRef,
  favoriteOnly,
}: {
  onUseAsRef: (img: { url: string; asset_id?: string; thumbnail?: string | null }) => void;
  favoriteOnly: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["assets-grid", favoriteOnly],
    queryFn: () =>
      api.listAssets({
        favorite: favoriteOnly ? true : undefined,
        limit: 100,
      }),
  });

  const toggleFav = useMutation({
    mutationFn: ({ id, fav }: { id: string; fav: boolean }) =>
      api.setAssetFavorite(id, fav),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets-grid"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  if (isLoading) {
    return (
      <div className="text-center py-12 text-txt-3 text-[12px]">
        {t("common.loading")}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="text-center py-16 text-txt-3 text-[12px]">
        {favoriteOnly ? t("assets.emptyFavorite") : t("assets.empty")}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2">
      {data.items.map((a) => (
        <div
          key={a.id}
          className="group relative aspect-square overflow-hidden rounded-s border border-line bg-bg-0 hover:border-[var(--acc)] transition-colors"
        >
          <img
            src={a.thumbnail || a.uri}
            alt={a.id}
            className="w-full h-full object-cover pixelated"
          />
          {/* 收藏 ★ */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              toggleFav.mutate({ id: a.id, fav: !a.favorite });
            }}
            title={a.favorite ? t("record.unfavorite") : t("record.favorite")}
            className="absolute top-1.5 right-1.5 w-7 h-7 grid place-items-center rounded-full bg-black/55 hover:bg-black/75 backdrop-blur-sm text-white text-[12px] transition-colors"
            style={a.favorite ? { color: "var(--amber)" } : undefined}
          >
            {a.favorite ? "★" : "☆"}
          </button>

          {/* hover 时显示作为参考图 */}
          <button
            type="button"
            onClick={() =>
              onUseAsRef({
                url: a.uri,
                asset_id: a.id,
                thumbnail: a.thumbnail,
              })
            }
            className="absolute inset-x-0 bottom-0 px-2 py-1.5 bg-black/65 backdrop-blur-sm text-[10.5px] text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1.5"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="m21 15-5-5L5 21" />
            </svg>
            {t("record.useAsRef")}
          </button>
        </div>
      ))}
    </div>
  );
}

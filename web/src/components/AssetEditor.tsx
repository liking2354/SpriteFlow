/**
 * AssetEditor — 素材编辑器内核组件
 *
 * 重构为双选项卡模式：
 *  - "基础工具"：filerobot-image-editor 裁剪/旋转/翻转/绘制/调色 + imgly 抠图
 *  - "AI 处理"：火山引擎 AI MediaKit 7 种图像处理
 *
 * 架构：作为普通页面级组件嵌入 `/editor` 路由页，
 *      不再使用 Portal/全屏蒙版，避免与 ImagePreview 等弹层组件嵌套冲突。
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import FilerobotImageEditor, {
  TABS,
  TOOLS,
} from "react-filerobot-image-editor";
import { removeBackground } from "@imgly/background-removal";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { filerobotZh, filerobotEn } from "@/i18n/filerobot";

type TabType = "basic" | "ai";

/** 把任意 URL 转成同源 blob: URL，避免 canvas 跨域污染 */
async function toLocalObjectUrl(url: string, assetId?: string | null): Promise<string> {
  const candidates: string[] = [];
  if (assetId) {
    candidates.push(`/api/assets/${encodeURIComponent(assetId)}/raw`);
  }
  candidates.push(`/api/proxy-image?url=${encodeURIComponent(url)}`);
  candidates.push(url);

  let lastErr: unknown = null;
  for (const c of candidates) {
    try {
      const res = await fetch(c, { credentials: "omit" });
      if (!res.ok) {
        lastErr = new Error(`${res.status} ${res.statusText} @ ${c}`);
        continue;
      }
      const blob = await res.blob();
      return URL.createObjectURL(blob);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

/** dataURL -> File */
function dataUrlToFile(dataUrl: string, filename: string): File {
  const [head, body] = dataUrl.split(",");
  const mime = /data:(.*?);base64/.exec(head)?.[1] || "image/png";
  const bin = atob(body);
  const len = bin.length;
  const arr = new Uint8Array(len);
  for (let i = 0; i < len; i++) arr[i] = bin.charCodeAt(i);
  return new File([arr], filename, { type: mime });
}

/** 抠图模型档位（imgly 实际枚举值） */
type ImglyModel = "isnet_quint8" | "isnet_fp16" | "isnet";

const MODEL_OPTIONS: Array<{ value: ImglyModel; sizeMB: number; tier: "fast" | "balanced" | "best" }> = [
  { value: "isnet_quint8", sizeMB: 22, tier: "fast" },
  { value: "isnet_fp16", sizeMB: 44, tier: "balanced" },
  { value: "isnet", sizeMB: 88, tier: "best" },
];

/** imgly background-removal 本地模型路径 */
const IMGLY_PUBLIC_PATH =
  typeof window !== "undefined"
    ? `${window.location.origin}/imgly/`
    : "/imgly/";

/** filerobot 暗色主题 palette */
const FILEROBOT_DARK_PALETTE = {
  "txt-primary": "#e8ecf4",
  "txt-secondary": "#a8b1c4",
  "txt-secondary-invert": "#0e1116",
  "txt-placeholder": "#6b7388",
  "txt-warning": "#f6b945",
  "txt-error": "#ff5b6e",
  "txt-info": "#5fb6ff",
  "accent-primary": "#5b8cff",
  "accent-primary-hover": "#7aa2ff",
  "accent-primary-active": "#5b8cff",
  "accent-primary-disabled": "rgba(91, 140, 255, 0.35)",
  "accent-secondary-disabled": "rgba(91, 140, 255, 0.18)",
  "accent-stateless": "#5b8cff",
  "accent-stateless_0_4_opacity": "rgba(91,140,255,0.4)",
  "accent_0_5_5_opacity": "rgba(91,140,255,0.55)",
  "accent_0_5_opacity": "rgba(91,140,255,0.5)",
  "accent_0_7_opacity": "rgba(91,140,255,0.7)",
  "accent_1_2_opacity": "rgba(91,140,255,0.12)",
  "accent_1_8_opacity": "rgba(91,140,255,0.18)",
  "accent_4_0_opacity": "rgba(91,140,255,0.40)",
  "bg-primary": "#0e1116",
  "bg-primary-light": "#161b24",
  "bg-primary-hover": "#1c2230",
  "bg-primary-active": "#212939",
  "bg-primary-stateless": "#161b24",
  "bg-primary-0-5-opacity": "rgba(14,17,22,0.5)",
  "bg-secondary": "#161b24",
  "bg-grey": "#0a0d12",
  "bg-stateless": "#0e1116",
  "bg-active": "#1c2230",
  "bg-base-light": "#1c2230",
  "bg-base-medium": "#212939",
  "bg-hover": "#1c2230",
  "bg-green": "#163b2e",
  "bg-green-medium": "#1f5142",
  "bg-blue": "#152a4a",
  "bg-red": "#3b1620",
  "bg-red-light": "#4a1a26",
  "background-red-medium": "#5a1f30",
  "bg-orange": "#3b2a16",
  "bg-tooltip": "#212939",
  "icon-primary": "#e8ecf4",
  "icons-primary-opacity-0-6": "rgba(232,236,244,0.6)",
  "icons-secondary": "#a8b1c4",
  "icons-placeholder": "#6b7388",
  "icons-invert": "#0e1116",
  "icons-muted": "#6b7388",
  "icons-primary-hover": "#ffffff",
  "icons-secondary-hover": "#e8ecf4",
  "btn-primary-text": "#ffffff",
  "btn-primary-text-0-6": "rgba(255,255,255,0.6)",
  "btn-primary-text-0-4": "rgba(255,255,255,0.4)",
  "btn-disabled-text": "#6b7388",
  "btn-secondary-text": "#e8ecf4",
  "link-primary": "#5b8cff",
  "link-stateless": "#5b8cff",
  "link-hover": "#7aa2ff",
  "link-active": "#5b8cff",
  "link-muted": "#6b7388",
  "link-pressed": "#3a6fe0",
  link: "#5b8cff",
  "borders-primary": "#262d3d",
  "borders-primary-hover": "#3a4258",
  "borders-secondary": "#1c2230",
  "borders-strong": "#3a4258",
  "borders-invert": "#e8ecf4",
  "border-hover-bottom": "#5b8cff",
  "border-active-bottom": "#5b8cff",
  "border-primary-stateless": "#262d3d",
  "borders-disabled": "#1c2230",
  "borders-button": "#262d3d",
  "borders-item": "#262d3d",
  "borders-base-light": "#262d3d",
  "borders-base-medium": "#3a4258",
  "borders-green": "#1f5142",
  "borders-green-medium": "#2a6b58",
  "borders-red": "#5a1f30",
  "active-secondary": "#1c2230",
  "active-secondary-hover": "#212939",
  tag: "#212939",
  "states-error-disabled-text": "#6b7388",
  error: "#ff5b6e",
  "error-0-28-opacity": "rgba(255,91,110,0.28)",
  "error-0-12-opacity": "rgba(255,91,110,0.12)",
  "error-hover": "#ff7585",
  "error-active": "#e34b5e",
  success: "#3ad29f",
  "success-hover": "#5fdfb1",
  "success-Active": "#2cb88a",
  warning: "#f6b945",
  "warning-hover": "#ffc55a",
  "warning-active": "#dca435",
  info: "#5fb6ff",
  modified: "#f6b945",
  red: "#ff5b6e",
  orange: "#ff9f43",
  salad: "#7ddc88",
  green: "#3ad29f",
  blue: "#5b8cff",
  indigo: "#7c69ef",
  violet: "#b07bff",
  pink: "#ff6fa8",
  "gradient-right": "linear-gradient(90deg, transparent, rgba(91,140,255,0.18))",
  "extra-0-3-overlay": "rgba(0,0,0,0.3)",
  "gradient-right-active": "linear-gradient(90deg, transparent, rgba(91,140,255,0.28))",
  "gradient-right-hover": "linear-gradient(90deg, transparent, rgba(91,140,255,0.22))",
  "extra-0-5-overlay": "rgba(0,0,0,0.5)",
  "extra-0-7-overlay": "rgba(0,0,0,0.7)",
  "extra-0-9-overlay": "rgba(0,0,0,0.9)",
  "red-0-1-overlay": "rgba(255,91,110,0.1)",
  "orange-0-1-overlay": "rgba(255,159,67,0.1)",
  "accent-0-8-overlay": "rgba(91,140,255,0.8)",
  "green-0-2-Overlay": "rgba(58,210,159,0.2)",
  camera: "#a8b1c4",
  "google-drive": "#a8b1c4",
  dropbox: "#a8b1c4",
  "one-drive": "#a8b1c4",
  device: "#a8b1c4",
};

/** AI 处理能力定义 */
const AI_CAPABILITIES: Array<{
  id: string;
  icon: string;
  labelKey: string;
  descKey: string;
}> = [
  { id: "enhance_photo", icon: "✨", labelKey: "editor.ai.enhance", descKey: "editor.ai.enhanceDesc" },
  { id: "image_inpaint", icon: "🎨", labelKey: "editor.ai.inpaint", descKey: "editor.ai.inpaintDesc" },
  { id: "remove_bg", icon: "✂️", labelKey: "editor.ai.removeBg", descKey: "editor.ai.removeBgDesc" },
  { id: "image_cut", icon: "🖼️", labelKey: "editor.ai.cut", descKey: "editor.ai.cutDesc" },
  { id: "image_outpaint", icon: "🔲", labelKey: "editor.ai.outpaint", descKey: "editor.ai.outpaintDesc" },
  { id: "slim_image", icon: "📐", labelKey: "editor.ai.slim", descKey: "editor.ai.slimDesc" },
  { id: "resize_image", icon: "↔️", labelKey: "editor.ai.resize", descKey: "editor.ai.resizeDesc" },
];

interface SaveResult {
  imageBase64?: string;
  imageData?: { imageBase64?: string; fullName?: string; mimeType?: string; name?: string; extension?: string };
  fullName?: string;
  mimeType?: string;
  name?: string;
  extension?: string;
}

interface Props {
  url: string;
  parentAssetId?: string | null;
  onSaved?: (asset: AssetItem) => void;
}

export function AssetEditor({ url, parentAssetId, onSaved }: Props) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<TabType>("basic");
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [bgRemoving, setBgRemoving] = useState(false);
  const [bgProgress, setBgProgress] = useState(0);
  const [saving, setSaving] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [actionInfo, setActionInfo] = useState<string | null>(null);
  const [bgModel, setBgModel] = useState<ImglyModel>("isnet_quint8");
  const [aiProcessing, setAiProcessing] = useState<string | null>(null);
  const [aiResultUrl, setAiResultUrl] = useState<string | null>(null);

  const filerobotTranslations = useMemo(() => {
    return i18n.language?.startsWith("zh") ? filerobotZh : filerobotEn;
  }, [i18n.language]);

  // 加载图片
  useEffect(() => {
    let cancelled = false;
    let createdUrl: string | null = null;
    setLocalUrl(null);
    setLoadErr(null);
    setActionErr(null);
    (async () => {
      try {
        const objUrl = await toLocalObjectUrl(url, parentAssetId);
        if (cancelled) {
          URL.revokeObjectURL(objUrl);
          return;
        }
        createdUrl = objUrl;
        setLocalUrl(objUrl);
      } catch (e) {
        setLoadErr(String(e));
      }
    })();
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [url, parentAssetId]);

  // AI 处理 mutation
  const aiProcessMutation = useMutation({
    mutationFn: async (params: { capability: string; extra?: Record<string, unknown> }) => {
      if (!parentAssetId) throw new Error("parentAssetId required");
      return api.aiProcess(parentAssetId, params.capability, params.extra || {});
    },
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      queryClient.invalidateQueries({ queryKey: ["assets-grid"] });
      // 下载结果图用于预览
      fetch(`/api/assets/${encodeURIComponent(asset.id)}/raw`)
        .then((res) => res.ok ? res.blob() : null)
        .then((blob) => {
          if (blob) {
            const newUrl = URL.createObjectURL(blob);
            setAiResultUrl(newUrl);
          }
        });
      setActionInfo(t("editor.ai.processed", "AI 处理完成"));
      setTimeout(() => setActionInfo(null), 3000);
    },
    onError: (err: Error) => {
      setActionErr(`${t("editor.ai.processFailed", "AI 处理失败")}: ${err.message}`);
    },
  });

  const upload = useMutation({
    mutationFn: async ({ file, tag }: { file: File; tag: string }) => {
      return api.uploadAsset(file, tag, parentAssetId || undefined);
    },
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      queryClient.invalidateQueries({ queryKey: ["assets-grid"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["asset-detail", asset.id] });
      setActionInfo(t("editor.savedNew"));
      setTimeout(() => setActionInfo(null), 3000);
      onSaved?.(asset);
    },
  });

  const handleSave = async (saved: SaveResult) => {
    try {
      setActionErr(null);
      setSaving(true);
      const b64 = saved.imageBase64 || saved.imageData?.imageBase64;
      const fullName =
        saved.fullName ||
        saved.imageData?.fullName ||
        `${saved.name || "edited"}.${saved.extension || "png"}`;
      if (!b64) throw new Error("editor returned no image");
      const file = dataUrlToFile(b64, fullName);
      await upload.mutateAsync({ file, tag: "edited" });
    } catch (e) {
      setActionErr(`${t("editor.saveFailed")}: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveBg = async () => {
    if (!localUrl || bgRemoving) return;
    try {
      setActionErr(null);
      setBgRemoving(true);
      setBgProgress(0);
      const blob = await removeBackground(localUrl, {
        publicPath: IMGLY_PUBLIC_PATH,
        model: bgModel,
        progress: (_key: string, current: number, total: number) => {
          if (total > 0) setBgProgress(Math.round((current / total) * 100));
        },
      });
      const newUrl = URL.createObjectURL(blob);
      if (localUrl.startsWith("blob:")) URL.revokeObjectURL(localUrl);
      setLocalUrl(newUrl);
    } catch (e) {
      setActionErr(`${t("editor.removeBgFailed")}: ${String(e)}`);
    } finally {
      setBgRemoving(false);
      setBgProgress(0);
    }
  };

  const handleAIProcess = (capability: string, extra?: Record<string, unknown>) => {
    if (!parentAssetId || aiProcessing) return;
    setAiProcessing(capability);
    aiProcessMutation.mutate(
      { capability, extra },
      {
        onSuccess: () => setAiProcessing(null),
        onError: () => setAiProcessing(null),
      }
    );
  };

  return (
    <div className="flex flex-col h-full min-h-0 rounded-l overflow-hidden border border-line bg-bg-1">
      {/* 顶部工具条：选项卡切换 */}
      <div className="h-12 px-4 flex items-center gap-2 border-b border-line bg-bg-1/95 flex-shrink-0">
        <div className="flex items-center gap-1 bg-bg-3 rounded-s p-0.5">
          <button
            type="button"
            onClick={() => setTab("basic")}
            className={`px-3 h-7 rounded-s text-[11.5px] transition-colors ${
              tab === "basic"
                ? "bg-acc text-white"
                : "text-txt-2 hover:text-txt-1"
            }`}
          >
            {t("editor.tabBasic", "基础工具")}
          </button>
          <button
            type="button"
            onClick={() => setTab("ai")}
            className={`px-3 h-7 rounded-s text-[11.5px] transition-colors ${
              tab === "ai"
                ? "bg-acc text-white"
                : "text-txt-2 hover:text-txt-1"
            }`}
          >
            {t("editor.tabAI", "AI 处理")}
          </button>
        </div>

        <span className="text-[12.5px] text-txt-2 ml-3">
          {tab === "basic" ? t("editor.subtitle") : t("editor.ai.subtitle", "火山引擎 AI 图像处理")}
        </span>

        <div className="ml-auto flex items-center gap-2">
          {tab === "basic" && (
            <>
              <label
                className="flex items-center gap-1.5 h-8 pl-2.5 pr-1.5 rounded-s border border-line bg-bg-3 text-[11px] text-txt-2"
                title={t("editor.modelHint")}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M7 12h10M10 18h4" />
                </svg>
                <span className="text-txt-3">{t("editor.modelLabel")}</span>
                <select
                  value={bgModel}
                  onChange={(e) => setBgModel(e.target.value as ImglyModel)}
                  disabled={bgRemoving}
                  className="bg-transparent text-[11.5px] text-txt-1 outline-none cursor-pointer disabled:cursor-not-allowed"
                  style={{ appearance: "none" }}
                >
                  {MODEL_OPTIONS.map((opt) => (
                    <option
                      key={opt.value}
                      value={opt.value}
                      style={{ background: "#161b24", color: "#e8ecf4" }}
                    >
                      {t(`editor.modelTier.${opt.tier}`)} · {opt.sizeMB}MB
                    </option>
                  ))}
                </select>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="opacity-60">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </label>

              <button
                type="button"
                onClick={handleRemoveBg}
                disabled={!localUrl || bgRemoving || saving}
                className="flex items-center gap-1.5 px-3 h-8 rounded-s border border-line bg-bg-3 text-[11.5px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={t("editor.removeBgHint")}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4l16 16M4 20L20 4" />
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                </svg>
                {bgRemoving ? `${t("editor.removing")} ${bgProgress}%` : t("editor.removeBg")}
              </button>
            </>
          )}
        </div>
      </div>

      {/* 抠图进度条 */}
      {bgRemoving && (
        <div className="h-1 bg-bg-2 relative overflow-hidden flex-shrink-0">
          <div
            className="absolute inset-y-0 left-0 transition-all"
            style={{
              width: `${bgProgress}%`,
              background: "linear-gradient(90deg, var(--acc), var(--cyan), var(--violet))",
            }}
          />
        </div>
      )}

      {/* AI 处理中 / 完成提示 */}
      {aiProcessing && (
        <div className="px-4 py-2 bg-[var(--acc)]/10 border-b border-[var(--acc)]/30 text-[12px] text-[var(--acc)] flex items-center gap-2 flex-shrink-0">
          <span className="animate-pulse">{AI_CAPABILITIES.find(c => c.id === aiProcessing)?.icon}</span>
          <span>{t(`editor.ai.processing`, "AI 处理中...")}</span>
        </div>
      )}
      {aiResultUrl && !aiProcessing && (
        <div className="px-4 py-2 bg-[var(--green)]/10 border-b border-[var(--green)]/30 text-[12px] text-[var(--green)] flex items-center gap-2 flex-shrink-0">
          <span>{t("editor.ai.resultReady", "AI 处理结果已生成，可在右侧查看")}</span>
        </div>
      )}

      {/* 操作错误/成功提示 */}
      {actionErr && (
        <div className="px-4 py-2 bg-[var(--red)]/10 border-b border-[var(--red)]/30 text-[12px] text-[var(--red)] flex items-start gap-2 flex-shrink-0">
          <span className="flex-1 break-all">⚠ {actionErr}</span>
          <button type="button" onClick={() => setActionErr(null)} className="text-txt-2 hover:text-txt-0">✕</button>
        </div>
      )}
      {actionInfo && (
        <div
          className="px-4 py-2 border-b text-[12px] flex items-start gap-2 flex-shrink-0"
          style={{ background: "rgba(58,210,159,0.08)", borderColor: "rgba(58,210,159,0.3)", color: "var(--green)" }}
        >
          <span className="flex-1 break-all">✓ {actionInfo}</span>
          <button type="button" onClick={() => setActionInfo(null)} className="text-txt-2 hover:text-txt-0">✕</button>
        </div>
      )}

      {/* 主体：根据选项卡切换内容 */}
      <div className="flex-1 min-h-0 relative">
        {loadErr && (
          <div className="absolute inset-0 grid place-items-center text-[var(--red)] text-[13px] p-6 text-center">
            {t("editor.loadFailed")}: {loadErr}
          </div>
        )}

        {!loadErr && !localUrl && (
          <div className="absolute inset-0 grid place-items-center text-txt-2 text-[12px]">
            {t("editor.loading")}
          </div>
        )}

        {/* 基础工具面板：filerobot 编辑器 */}
        {tab === "basic" && localUrl && (
          <FilerobotImageEditor
            key={localUrl}
            source={localUrl}
            onSave={(saved: any) => handleSave(saved)}
            onBeforeSave={() => false}
            defaultSavedImageType="png"
            defaultSavedImageName="edited"
            tabsIds={[TABS.ADJUST, TABS.ANNOTATE, TABS.WATERMARK, TABS.FILTERS, TABS.FINETUNE, TABS.RESIZE]}
            defaultTabId={TABS.ADJUST}
            defaultToolId={TOOLS.CROP}
            useBackendTranslations={false}
            savingPixelRatio={1}
            previewPixelRatio={window.devicePixelRatio || 1}
            avoidChangesNotSavedAlertOnLeave
            backgroundColor="transparent"
            theme={{ palette: FILEROBOT_DARK_PALETTE, typography: { fontFamily: "inherit" } }}
            translations={filerobotTranslations}
            Crop={{
              presetsItems: [
                { titleKey: "1:1 Square", width: 1, height: 1 },
                { titleKey: "4:3", width: 4, height: 3 },
                { titleKey: "16:9", width: 16, height: 9 },
                { titleKey: "9:16", width: 9, height: 16 },
                { titleKey: "Sprite 32×32", width: 32, height: 32 },
                { titleKey: "Sprite 64×64", width: 64, height: 64 },
                { titleKey: "Sprite 128×128", width: 128, height: 128 },
              ],
            }}
          />
        )}

        {/* AI 处理面板：左侧功能菜单 + 右侧图片预览 */}
        {tab === "ai" && (
          <div className="h-full flex overflow-hidden">
            {/* 左侧：AI 能力菜单 */}
            <div className="w-[220px] flex-shrink-0 border-r border-line bg-bg-1 flex flex-col overflow-y-auto">
              <div className="px-3 py-2.5 text-[10.5px] text-txt-3 border-b border-line uppercase tracking-wider">
                {t("editor.ai.panelTitle", "AI 能力")}
              </div>
              <div className="flex-1 py-1.5 space-y-0.5">
                {AI_CAPABILITIES.map((cap) => (
                  <button
                    key={cap.id}
                    type="button"
                    onClick={() => handleAIProcess(cap.id)}
                    disabled={aiProcessing !== null}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 text-left text-[11.5px] transition-colors ${
                      aiProcessing === cap.id
                        ? "bg-[var(--acc)]/15 text-[var(--acc)] border-l-2 border-[var(--acc)]"
                        : "text-txt-2 hover:text-txt-1 hover:bg-bg-2 border-l-2 border-transparent"
                    }`}
                  >
                    <span className="text-base w-5 text-center flex-shrink-0">{cap.icon}</span>
                    <div className="min-w-0">
                      <div className="font-medium text-[12px]">{t(cap.labelKey)}</div>
                      <div className="text-[10.5px] text-txt-3 leading-tight mt-0.5">{t(cap.descKey)}</div>
                    </div>
                    {aiProcessing === cap.id && (
                      <span className="ml-auto animate-spin text-[10px]">⟳</span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* 右侧：图片预览区 */}
            <div className="flex-1 min-w-0 flex flex-col bg-bg-0">
              {localUrl ? (
                <div className="flex-1 flex flex-col items-center justify-center p-6 gap-4 overflow-auto">
                  {/* 主预览：当前图 or 对比 */}
                  {aiResultUrl ? (
                    <div className="w-full max-w-[640px] flex flex-col items-center gap-3">
                      <div className="grid grid-cols-2 gap-4 w-full">
                        <div className="flex flex-col items-center gap-1.5">
                          <span className="text-[10.5px] text-txt-3">{t("editor.ai.original", "原图")}</span>
                          <div className="w-full aspect-square rounded-lg border border-line bg-bg-3 grid place-items-center overflow-hidden">
                            <img src={localUrl} alt="original" className="max-w-full max-h-full object-contain" />
                          </div>
                        </div>
                        <div className="flex flex-col items-center gap-1.5">
                          <span className="text-[10.5px] text-[var(--green)]">✓ {t("editor.ai.result", "结果")}</span>
                          <div className="w-full aspect-square rounded-lg border border-[var(--green)]/40 bg-bg-3 grid place-items-center overflow-hidden">
                            <img src={aiResultUrl} alt="result" className="max-w-full max-h-full object-contain" />
                          </div>
                        </div>
                      </div>
                      <span className="text-[10.5px] text-[var(--green)]">
                        {t("editor.ai.resultSaved", "结果已自动保存到素材库")}
                      </span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      <div className="rounded-lg border border-line bg-bg-3 grid place-items-center overflow-hidden" style={{ maxWidth: "600px", maxHeight: "480px" }}>
                        <img src={localUrl} alt="preview" className="max-w-full max-h-[480px] object-contain" />
                      </div>
                      <span className="text-[11px] text-txt-3">
                        {t("editor.ai.selectHint", "从左侧选择 AI 能力开始处理")}
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex-1 grid place-items-center text-[12px] text-txt-3">
                  {loadErr ? `${t("editor.loadFailed")}: ${loadErr}` : t("editor.loading")}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

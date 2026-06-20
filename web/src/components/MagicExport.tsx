/**
 * MAGIC 二次处理导出组件
 *
 * Real-ESRGAN anime x4 超分 → 缩小为 1/2, 1/4, 1/8 三种透明 PNG 变体
 *
 * 用法:
 *   <MagicExport frames={pngBlobs} label="sprite-sheet" />
 *
 * Props:
 *   getFrames: 返回待处理的帧 PNG Blob 数组的异步函数
 *   label: 任务标签（用于后端区分来源）
 */

import { useState, useCallback, useRef } from "react";

interface VariantInfo {
  key: string;
  label: string;
  scale: number;
  output_size?: [number, number] | null;
}

interface MagicResult {
  magic_id?: string;
  frames_count?: number;
  source_size?: { width: number; height: number };
  resize_mode?: string;
  variants?: VariantInfo[];
}

interface MagicStatusResult {
  magic_id: string;
  status: string;
  frames_count: number;
  source_size?: { width: number; height: number };
  resize_mode?: string;
  variants: (VariantInfo & { frame_count: number })[];
}

interface MagicExportProps {
  getFrames: () => Promise<Blob[]>;
  label?: string;
  disabled?: boolean;
}

const VARIANT_DISPLAY: Record<string, { label: string; desc: string }> = {
  half:    { label: "MAGIC 1/2", desc: "画布为原尺寸 ½" },
  quarter: { label: "MAGIC 1/4", desc: "画布为原尺寸 ¼" },
  eighth:  { label: "MAGIC 1/8", desc: "画布为原尺寸 ⅛" },
};

export function MagicExport({ getFrames, label = "export", disabled = false }: MagicExportProps) {
  const [resizeMode, setResizeMode] = useState<"hard" | "soft">("hard");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<MagicResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeFrameIdx, setActiveFrameIdx] = useState(0);
  const [variantImages, setVariantImages] = useState<Record<string, string>>({});
  const [loadingVariant, setLoadingVariant] = useState<string | null>(null);
  const abortRef = useRef(false);

  // ---- 上传并处理 ----
  const handleMagic = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setVariantImages({});
    abortRef.current = false;

    try {
      const frames = await getFrames();
      if (frames.length === 0) {
        throw new Error("没有可处理的帧");
      }

      const formData = new FormData();
      formData.append("label", label);
      formData.append("resize_mode", resizeMode);
      for (let i = 0; i < frames.length; i++) {
        formData.append("frames", frames[i], `frame_${i.toString().padStart(4, "0")}.png`);
      }

      const resp = await fetch("/api/magic/process-upload", {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) {
        const detail = (await resp.json().catch(() => ({}))) as { detail?: string };
        throw new Error(detail.detail || `HTTP ${resp.status}`);
      }

      const data = (await resp.json()) as MagicResult;
      if (abortRef.current) return;
      setResult(data);

      // 加载第一帧的各变体预览
      if (data.magic_id && data.variants) {
        for (const v of data.variants) {
          if (abortRef.current) break;
          setLoadingVariant(v.key);
          try {
            const imgResp = await fetch(
              `/api/magic/${data.magic_id}/frames/${v.key}/frame_0000.png`
            );
            if (imgResp.ok) {
              const blob = await imgResp.blob();
              setVariantImages(prev => ({ ...prev, [v.key]: URL.createObjectURL(blob) }));
            }
          } catch { /* ignore */ }
          setLoadingVariant(null);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [busy, getFrames, label, resizeMode]);

  // ---- 导出指定变体 ZIP ----
  const handleExport = useCallback(
    async (variantKey: string) => {
      if (!result?.magic_id) return;
      try {
        const a = document.createElement("a");
        a.href = `/api/magic/${result.magic_id}/export/${variantKey}`;
        a.download = `magic-${variantKey}-frames.zip`;
        a.click();
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [result]
  );

  const canRun = !busy && !disabled;

  return (
    <div className="space-y-3">
      {/* ---- 缩放模式选择 + MAGIC 按钮 ---- */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-[var(--txt-2)]">缩放模式:</span>
        <label className="flex items-center gap-1 text-xs cursor-pointer">
          <input
            type="radio"
            name="magicResize"
            checked={resizeMode === "hard"}
            onChange={() => setResizeMode("hard")}
            disabled={busy}
          />
          <span style={{ color: resizeMode === "hard" ? "var(--acc)" : "var(--txt-2)" }}>
            硬 (像素边缘)
          </span>
        </label>
        <label className="flex items-center gap-1 text-xs cursor-pointer">
          <input
            type="radio"
            name="magicResize"
            checked={resizeMode === "soft"}
            onChange={() => setResizeMode("soft")}
            disabled={busy}
          />
          <span style={{ color: resizeMode === "soft" ? "var(--acc)" : "var(--txt-2)" }}>
            软 (平滑抗锯齿)
          </span>
        </label>

        <button
          onClick={handleMagic}
          disabled={!canRun}
          className="px-4 py-1.5 rounded-lg text-sm font-medium transition-all ml-auto"
          style={{
            background: canRun ? "#f59e0b" : "var(--line)",
            color: canRun ? "#fff" : "var(--txt-3)",
            cursor: canRun ? "pointer" : "not-allowed",
          }}
        >
          {busy ? (
            <span className="flex items-center gap-1">
              <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity=".3" />
                <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" fill="none" />
              </svg>
              MAGIC 处理中...
            </span>
          ) : (
            "✨ MAGIC"
          )}
        </button>
      </div>

      {/* ---- 错误提示 ---- */}
      {error && (
        <div className="text-xs p-2 rounded" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-2 underline"
            style={{ color: "#ef4444" }}
          >
            关闭
          </button>
        </div>
      )}

      {/* ---- 结果变体面板 ---- */}
      {result?.variants && result.variants.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {result.variants.map((v) => {
            const display = VARIANT_DISPLAY[v.key] || { label: v.label, desc: "" };
            const imgUrl = variantImages[v.key];
            const loading = loadingVariant === v.key;

            return (
              <div
                key={v.key}
                className="rounded-lg border p-3"
                style={{ background: "var(--bg-2)", borderColor: "var(--line)" }}
              >
                {/* 变体标签 */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold" style={{ color: "var(--txt-0)" }}>
                    {display.label}
                  </span>
                  <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>
                    {display.desc}
                  </span>
                </div>

                {/* 预览 Canvas */}
                <div
                  className="w-full aspect-square rounded flex items-center justify-center mb-2"
                  style={{
                    background: "repeating-conic-gradient(var(--bg-3) 0% 25%, transparent 0% 50%) 50% / 16px 16px",
                  }}
                >
                  {loading ? (
                    <span className="text-xs text-[var(--txt-3)]">加载中...</span>
                  ) : imgUrl ? (
                    <img
                      src={imgUrl}
                      alt={`MAGIC ${v.key}`}
                      className="max-w-full max-h-full object-contain"
                      style={{ imageRendering: resizeMode === "hard" ? "pixelated" : "auto" }}
                    />
                  ) : (
                    <span className="text-xs text-[var(--txt-3)]">-</span>
                  )}
                </div>

                {/* 输出尺寸 */}
                {v.output_size && (
                  <div className="text-[10px] mb-2" style={{ color: "var(--txt-2)" }}>
                    {v.output_size[0]} × {v.output_size[1]}
                  </div>
                )}

                {/* 导出按钮 */}
                <button
                  onClick={() => handleExport(v.key)}
                  disabled={busy}
                  className="w-full py-1 rounded text-xs font-medium transition-colors"
                  style={{
                    background: "var(--acc-soft)",
                    color: "var(--acc)",
                  }}
                >
                  下载 {display.label} ZIP
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

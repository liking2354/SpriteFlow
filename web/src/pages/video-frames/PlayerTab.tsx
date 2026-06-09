import { useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { FrameAnimationPreview } from "@/components/graph/FrameAnimationPreview";
import { FrameThumbnails } from "@/components/graph/FrameThumbnails";

interface FrameItem {
  dataUrl: string;
  timestamp?: number;
  width?: number;
  height?: number;
}

const cardBg: React.CSSProperties = { background: "var(--bg-1)", borderRadius: 8, border: "1px solid var(--line)" };
const accentBtn: React.CSSProperties = {
  background: "var(--acc)", color: "#fff", border: "none", borderRadius: 6,
  padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
};
const secondaryBtn: React.CSSProperties = {
  background: "var(--bg-3)", color: "var(--txt-1)", border: "1px solid var(--line)",
  borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer",
};
const inputStyle: React.CSSProperties = {
  background: "var(--bg-0)", border: "1px solid var(--line)", borderRadius: 5,
  color: "var(--txt-1)", padding: "5px 8px", fontSize: 12, outline: "none", width: 70,
};
const labelStyle: React.CSSProperties = { fontSize: 11, color: "var(--txt-3)", marginBottom: 2 };

export function PlayerTab() {
  const { t } = useTranslation();
  const [frames, setFrames] = useState<FrameItem[]>([]);
  const [fps, setFps] = useState(12);
  const [selected, setSelected] = useState<boolean[]>([]);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (files: FileList) => {
    const fileArr = Array.from(files).sort((a, b) => a.name.localeCompare(b.name));
    const newFrames: FrameItem[] = [];
    let loaded = 0;
    fileArr.forEach((f) => {
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image();
        img.onload = () => {
          newFrames.push({
            dataUrl: reader.result as string,
            width: img.naturalWidth,
            height: img.naturalHeight,
          });
          loaded++;
          if (loaded === fileArr.length) {
            setFrames([...newFrames]);
            setSelected(newFrames.map(() => true));
          }
        };
        img.src = reader.result as string;
      };
      reader.readAsDataURL(f);
    });
  };

  const handleFileInput = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) handleFiles(e.target.files);
  };

  const clearFrames = () => {
    setFrames([]);
    setSelected([]);
  };

  const exportGif = async () => {
    const activeFrames = frames.filter((_, i) => selected[i]);
    if (!activeFrames.length) return;
    try {
      const { GIFEncoder, quantize, applyPalette } = await import("gifenc");
      const w = activeFrames[0].width ?? 64, h = activeFrames[0].height ?? 64;
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      const gif = GIFEncoder();
      let palette: any = null;
      for (const f of activeFrames) {
        ctx.clearRect(0, 0, w, h);
        const img = new Image();
        await new Promise<void>((resolve) => {
          img.onload = () => {
            ctx.drawImage(img, 0, 0, w, h);
            resolve();
          };
          img.src = f.dataUrl;
        });
        const fd = ctx.getImageData(0, 0, w, h);
        if (!palette) palette = quantize(fd, 256);
        gif.writeFrame(applyPalette(fd, palette), w, h, { palette, delay: Math.round(1000 / fps) });
      }
      gif.finish();
      const blob = new Blob([gif.bytes()], { type: "image/gif" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "animation.gif";
      a.click();
    } catch { alert("需安装 gifenc: npm i gifenc"); }
  };

  const toggleSelect = (i: number, checked: boolean) => {
    const next = [...selected];
    next[i] = checked;
    setSelected(next);
  };

  const activeFrames = frames.filter((_, i) => selected[i] ?? true);

  return (
    <div style={{ maxWidth: 800 }}>
      {/* 上传区 */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
        }}
        style={{ ...cardBg, padding: 24, textAlign: "center", borderColor: dragOver ? "var(--acc)" : "var(--line)", marginBottom: 16 }}
      >
        <div style={{ fontSize: 28, marginBottom: 8 }}>🎞</div>
        <div style={{ fontSize: 13, color: "var(--txt-2)", marginBottom: 4 }}>
          {t("videoFrames.player.dropHint")}
        </div>
        <div style={{ fontSize: 10, color: "var(--txt-3)", marginBottom: 12 }}>
          PNG / JPG / WebP 序列帧
        </div>
        <input
          type="file"
          accept="image/*"
          multiple
          onChange={handleFileInput}
          style={{ display: "none" }}
          id="vf-player-upload"
        />
        <label htmlFor="vf-player-upload" style={{ ...accentBtn, display: "inline-block", cursor: "pointer" }}>
          选择帧图片
        </label>
      </div>

      {frames.length === 0 ? (
        <div style={{ ...cardBg, padding: 32, textAlign: "center" }}>
          <div style={{ fontSize: 14, color: "var(--txt-3)" }}>{t("videoFrames.player.noFrames")}</div>
        </div>
      ) : (
        <>
          {/* FPS 设置 + 操作栏 */}
          <div style={{ ...cardBg, padding: 12, marginBottom: 12, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={labelStyle}>FPS:</span>
              <input
                type="number"
                value={fps}
                onChange={(e) => setFps(Math.max(1, Math.min(60, Number(e.target.value))))}
                min={1}
                max={60}
                style={inputStyle}
              />
            </div>
            <div style={{ fontSize: 11, color: "var(--txt-3)" }}>
              共 {frames.length} 帧 · 已选 {selected.filter(Boolean).length} 帧
            </div>
            <div style={{ flex: 1 }} />
            <button onClick={clearFrames} style={secondaryBtn}>清空</button>
            <button onClick={exportGif} style={accentBtn} disabled={!selected.some(Boolean)}>
              导出 GIF
            </button>
          </div>

          {/* 动画预览 */}
          {activeFrames.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <FrameAnimationPreview frames={activeFrames} fps={fps} defaultLoop={true} />
            </div>
          )}

          {/* 帧缩略图列表 */}
          <div style={{ ...cardBg, padding: 12 }}>
            <div style={{ fontSize: 12, color: "var(--txt-2)", marginBottom: 8, fontWeight: 600 }}>
              帧列表
            </div>
            <FrameThumbnails
              frames={frames}
              selected={frames.map((_, i) => selected[i] ?? false)}
              onSelectionChange={toggleSelect}
            />
          </div>
        </>
      )}
    </div>
  );
}

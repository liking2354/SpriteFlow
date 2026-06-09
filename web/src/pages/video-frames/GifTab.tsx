import { useState, useRef, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

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

export function GifTab() {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState("gif2frames");
  const subtabs = [
    { key: "gif2frames", label: t("videoFrames.gif.gif2frames") },
    { key: "frames2gif", label: t("videoFrames.gif.frames2gif") },
  ];
  return (
    <div>
      <div style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid var(--line)" }}>
        {subtabs.map((s) => (
          <button key={s.key} onClick={() => setSubTab(s.key)}
            style={{ padding: "6px 14px", fontSize: 12, fontWeight: subTab === s.key ? 600 : 400,
              cursor: "pointer", border: "none", borderBottom: subTab === s.key ? "2px solid var(--acc)" : "2px solid transparent",
              background: "transparent", color: subTab === s.key ? "var(--acc)" : "var(--txt-2)" }}>
            {s.label}
          </button>
        ))}
      </div>
      {subTab === "gif2frames" && <Gif2Frames />}
      {subTab === "frames2gif" && <Frames2Gif />}
    </div>
  );
}

function Gif2Frames() {
  const { t } = useTranslation();
  const [frames, setFrames] = useState<Array<{ dataUrl: string; delay: number }>>([]);
  const [parsed, setParsed] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const handleFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    try {
      const gif: any = await import("gifuct-js");
      const buf = await f.arrayBuffer();
      const gifData = gif.parseGIF(buf);
      const decompressed = gif.decompressFrames(gifData, true);
      const result = decompressed.map((frame: any) => {
        const c = document.createElement("canvas");
        c.width = frame.dims.width; c.height = frame.dims.height;
        const ctx = c.getContext("2d")!;
        const id = ctx.createImageData(frame.dims.width, frame.dims.height);
        id.data.set(frame.patch); ctx.putImageData(id, 0, 0);
        return { dataUrl: c.toDataURL("image/png"), delay: frame.delay ?? 100 };
      });
      setFrames(result); setParsed(true);
    } catch { alert("解析失败，请确认是有效 GIF。\n需安装 gifuct-js: npm i gifuct-js"); }
  };

  const downloadZip = async () => {
    try {
      const JSZip = (await import("jszip")).default;
      const zip = new JSZip();
      for (let i = 0; i < frames.length; i++) {
        const blob = await fetch(frames[i].dataUrl).then(r => r.blob());
        zip.file(`frame_${String(i + 1).padStart(4, "0")}.png`, blob);
      }
      const zipBlob = await zip.generateAsync({ type: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(zipBlob); a.download = "frames.zip"; a.click();
    } catch { alert("需安装 jszip: npm i jszip"); }
  };

  return (
    <div style={{ ...cardBg, padding: 16 }}>
      <input type="file" accept=".gif" onChange={handleFile} style={{ marginBottom: 12 }} />
      {parsed && (
        <>
          <div style={{ fontSize: 12, color: "var(--acc)", marginBottom: 8 }}>{t("videoFrames.gif.parseSuccess", { n: frames.length })}</div>
          <button onClick={downloadZip} style={accentBtn}>{t("videoFrames.gif.downloadZip")}</button>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 12 }}>
            {frames.map((f, i) => (
              <div key={i} style={{ textAlign: "center" }}>
                <img src={f.dataUrl} alt={`#${i + 1}`} style={{ width: 64, height: 64, objectFit: "contain", background: "#0d0d1a", borderRadius: 4, imageRendering: "pixelated" }} />
                <div style={{ fontSize: 9, color: "var(--txt-3)", marginTop: 2 }}>#{i + 1}</div>
              </div>
            ))}
          </div>
        </>
      )}
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
}

function Frames2Gif() {
  const { t } = useTranslation();
  const [imageFrames, setImageFrames] = useState<Array<{ dataUrl: string; img: HTMLImageElement }>>([]);
  const [delay, setDelay] = useState(100);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const handleFiles = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const newFrames: typeof imageFrames = [];
    let loaded = 0;
    files.forEach((f) => {
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image(); img.onload = () => { newFrames.push({ dataUrl: reader.result as string, img }); loaded++; if (loaded === files.length) setImageFrames([...newFrames]); };
        img.src = reader.result as string;
      };
      reader.readAsDataURL(f);
    });
  };

  const generateGif = async () => {
    if (!imageFrames.length) return;
    try {
      const { GIFEncoder, quantize, applyPalette } = await import("gifenc");
      const w = imageFrames[0].img.naturalWidth, h = imageFrames[0].img.naturalHeight;
      const canvas = document.createElement("canvas"); canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d")!; const gif = GIFEncoder();
      const frames: ImageData[] = [];
      for (const { img } of imageFrames) { ctx.clearRect(0, 0, w, h); ctx.drawImage(img, 0, 0); frames.push(ctx.getImageData(0, 0, w, h)); }
      const palette = quantize(frames[0], 256);
      for (const fd of frames) gif.writeFrame(applyPalette(fd, palette), w, h, { palette, delay });
      gif.finish();
      setPreviewUrl(URL.createObjectURL(new Blob([gif.bytes()], { type: "image/gif" })));
    } catch { alert("需安装 gifenc: npm i gifenc"); }
  };

  const moveFrame = (from: number, to: number) => {
    const arr = [...imageFrames]; const [item] = arr.splice(from, 1); arr.splice(to, 0, item); setImageFrames(arr);
  };

  return (
    <div style={{ ...cardBg, padding: 16 }}>
      <input type="file" accept="image/*" multiple onChange={handleFiles} style={{ marginBottom: 12 }} />
      {imageFrames.length > 0 && <>
        <div style={{ fontSize: 11, color: "var(--txt-3)", marginBottom: 8 }}>{t("videoFrames.gif.dragHint")}</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 }}>
          {imageFrames.map((f, i) => (
            <div key={i} style={{ textAlign: "center", cursor: "grab" }}>
              <div style={{ display: "flex", gap: 2, justifyContent: "center", marginBottom: 2 }}>
                <button disabled={i === 0} onClick={() => moveFrame(i, i - 1)} style={{ ...secondaryBtn, fontSize: 10, padding: "1px 4px" }}>◀</button>
                <button disabled={i === imageFrames.length - 1} onClick={() => moveFrame(i, i + 1)} style={{ ...secondaryBtn, fontSize: 10, padding: "1px 4px" }}>▶</button>
              </div>
              <img src={f.dataUrl} alt={`#${i + 1}`} style={{ width: 64, height: 64, objectFit: "contain", background: "#0d0d1a", borderRadius: 4 }} />
              <div style={{ fontSize: 9, color: "var(--txt-3)", marginTop: 2 }}>#{i + 1}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={labelStyle}>{t("videoFrames.gif.delay")}:</span>
          <input type="number" value={delay} onChange={(e) => setDelay(Number(e.target.value))} min={10} max={5000} step={10} style={inputStyle} />
          <span style={{ fontSize: 10, color: "var(--txt-3)" }}>ms</span>
        </div>
        <button onClick={generateGif} style={accentBtn}>{t("videoFrames.gif.generateGif")}</button>
      </>}
      {previewUrl && (
        <div style={{ marginTop: 12, textAlign: "center" }}>
          <div style={{ fontSize: 12, color: "var(--txt-2)", marginBottom: 6 }}>{t("videoFrames.gif.preview")}</div>
          <img src={previewUrl} alt="GIF" style={{ maxWidth: "100%", borderRadius: 6, border: "1px solid var(--line)" }} />
          <a href={previewUrl} download="output.gif" style={{ ...accentBtn, textDecoration: "none", display: "inline-block", fontSize: 12, marginTop: 8 }}>
            {t("videoFrames.gif.generateGif")}
          </a>
        </div>
      )}
    </div>
  );
}


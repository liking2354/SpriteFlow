import { useState, type ChangeEvent } from "react";
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

export function SpriteToolTab() {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState("split");
  const subtabs = [
    { key: "split", label: t("videoFrames.spriteTool.split") },
    { key: "stitch", label: t("videoFrames.gif.simpleStitch") },
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid var(--line)" }}>
        {subtabs.map((s) => (
          <button
            key={s.key}
            onClick={() => setSubTab(s.key)}
            style={{
              padding: "6px 14px", fontSize: 12,
              fontWeight: subTab === s.key ? 600 : 400,
              cursor: "pointer", border: "none",
              borderBottom: subTab === s.key ? "2px solid var(--acc)" : "2px solid transparent",
              background: "transparent",
              color: subTab === s.key ? "var(--acc)" : "var(--txt-2)",
            }}
          >
            {s.label}
          </button>
        ))}
      </div>
      {subTab === "split" && <SpriteSplit />}
      {subTab === "stitch" && <ImageStitch />}
    </div>
  );
}

/* ========== 精灵表切分 ========== */
function SpriteSplit() {
  const { t } = useTranslation();
  const [srcImg, setSrcImg] = useState<HTMLImageElement | null>(null);
  const [cols, setCols] = useState(4);
  const [rows, setRows] = useState(4);
  const [output, setOutput] = useState<string | null>(null);
  const [outputGif, setOutputGif] = useState<string | null>(null);

  const handleSheet = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => setSrcImg(img);
      img.src = reader.result as string;
    };
    reader.readAsDataURL(f);
  };

  const split = () => {
    if (!srcImg) return;
    const canvas = document.createElement("canvas");
    const cw = Math.floor(srcImg.naturalWidth / cols), ch = Math.floor(srcImg.naturalHeight / rows);
    canvas.width = cols * cw; canvas.height = rows * ch;
    const ctx = canvas.getContext("2d")!;
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++)
        ctx.drawImage(srcImg, c * cw, r * ch, cw, ch, c * cw, r * ch, cw, ch);
    setOutput(canvas.toDataURL("image/png"));
  };

  const toGif = async () => {
    if (!srcImg) return;
    try {
      const { GIFEncoder, quantize, applyPalette } = await import("gifenc");
      const cw = Math.floor(srcImg.naturalWidth / cols), ch = Math.floor(srcImg.naturalHeight / rows);
      const gif = GIFEncoder(); let palette: any = null;
      const canvas = document.createElement("canvas"); canvas.width = cw; canvas.height = ch;
      const ctx = canvas.getContext("2d")!;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          ctx.clearRect(0, 0, cw, ch);
          ctx.drawImage(srcImg, c * cw, r * ch, cw, ch, 0, 0, cw, ch);
          const fd = ctx.getImageData(0, 0, cw, ch);
          if (!palette) palette = quantize(fd, 256);
          gif.writeFrame(applyPalette(fd, palette), cw, ch, { palette, delay: 100 });
        }
      }
      gif.finish();
      setOutputGif(URL.createObjectURL(new Blob([gif.bytes()], { type: "image/gif" })));
    } catch { alert("需安装 gifenc: npm i gifenc"); }
  };

  return (
    <div style={{ ...cardBg, padding: 16 }}>
      <input type="file" accept="image/*" onChange={handleSheet} style={{ marginBottom: 12 }} />
      <div style={{ display: "flex", gap: 12, marginBottom: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div>
          <div style={labelStyle}>{t("videoFrames.spriteTool.cols")}</div>
          <input type="number" value={cols} onChange={(e) => setCols(Number(e.target.value))} min={1} max={64} style={inputStyle} />
        </div>
        <div>
          <div style={labelStyle}>{t("videoFrames.spriteTool.rows")}</div>
          <input type="number" value={rows} onChange={(e) => setRows(Number(e.target.value))} min={1} max={64} style={inputStyle} />
        </div>
        <button onClick={split} disabled={!srcImg} style={accentBtn}>{t("videoFrames.spriteTool.doSplit")}</button>
      </div>
      {srcImg && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--txt-3)", marginBottom: 4 }}>原图</div>
          <img src={srcImg.src} alt="Src" style={{ maxWidth: 300, borderRadius: 6, border: "1px solid var(--line)" }} />
        </div>
      )}
      {output && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--txt-3)", marginBottom: 4 }}>{t("videoFrames.spriteTool.preview")}</div>
          <img src={output} alt="Split" style={{ maxWidth: 400, borderRadius: 6, border: "1px solid var(--line)", imageRendering: "pixelated" }} />
          <div style={{ marginTop: 8 }}>
            <button onClick={toGif} style={{ ...accentBtn, marginRight: 8 }}>{t("videoFrames.spriteTool.generateGif")}</button>
            <a href={output} download="sprite_split.png" style={{ ...secondaryBtn, textDecoration: "none", display: "inline-block" }}>下载 PNG</a>
          </div>
        </div>
      )}
      {outputGif && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11, color: "var(--txt-3)", marginBottom: 4 }}>{t("videoFrames.spriteTool.outputGif")}</div>
          <img src={outputGif} alt="GIF" style={{ maxWidth: 400, borderRadius: 6, border: "1px solid var(--line)" }} />
          <a href={outputGif} download="output.gif" style={{ ...accentBtn, textDecoration: "none", display: "inline-block", fontSize: 12, marginTop: 8 }}>
            下载 GIF
          </a>
        </div>
      )}
    </div>
  );
}

/* ========== 简单拼接 ========== */
function ImageStitch() {
  const { t } = useTranslation();
  const [images, setImages] = useState<Array<{ src: string; img: HTMLImageElement }>>([]);
  const [mode, setMode] = useState<"vertical" | "horizontal" | "overlay">("vertical");
  const [output, setOutput] = useState<string | null>(null);

  const handleFiles = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const imgs: typeof images = []; let loaded = 0;
    files.forEach((f) => {
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image();
        img.onload = () => {
          imgs.push({ src: reader.result as string, img });
          loaded++;
          if (loaded === files.length) setImages([...imgs]);
        };
        img.src = reader.result as string;
      };
      reader.readAsDataURL(f);
    });
  };

  const stitch = () => {
    if (!images.length) return;
    const canvas = document.createElement("canvas");
    if (mode === "vertical") {
      const w = Math.max(...images.map(i => i.img.naturalWidth));
      const h = images.reduce((s, i) => s + i.img.naturalHeight, 0);
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      let y = 0;
      images.forEach(({ img }) => { ctx.drawImage(img, (w - img.naturalWidth) / 2, y); y += img.naturalHeight; });
    } else if (mode === "horizontal") {
      const w = images.reduce((s, i) => s + i.img.naturalWidth, 0);
      const h = Math.max(...images.map(i => i.img.naturalHeight));
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      let x = 0;
      images.forEach(({ img }) => { ctx.drawImage(img, x, (h - img.naturalHeight) / 2); x += img.naturalWidth; });
    } else {
      const w = Math.max(...images.map(i => i.img.naturalWidth));
      const h = Math.max(...images.map(i => i.img.naturalHeight));
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      images.forEach(({ img }) => { ctx.drawImage(img, (w - img.naturalWidth) / 2, (h - img.naturalHeight) / 2); });
    }
    setOutput(canvas.toDataURL("image/png"));
  };

  return (
    <div style={{ ...cardBg, padding: 16 }}>
      <input type="file" accept="image/*" multiple onChange={handleFiles} style={{ marginBottom: 12 }} />
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {(["vertical", "horizontal", "overlay"] as const).map(m => (
          <button key={m} onClick={() => setMode(m)}
            style={{
              ...secondaryBtn,
              background: mode === m ? "var(--acc)" : "var(--bg-3)",
              color: mode === m ? "#fff" : "var(--txt-1)",
              borderColor: mode === m ? "var(--acc)" : "var(--line)",
            }}
          >
            {t(`videoFrames.gif.stitch${m.charAt(0).toUpperCase() + m.slice(1)}`)}
          </button>
        ))}
      </div>
      {images.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 }}>
          {images.map(({ src }, i) => (
            <img key={i} src={src} alt="" style={{ width: 64, height: 64, objectFit: "contain", background: "#0d0d1a", borderRadius: 4 }} />
          ))}
        </div>
      )}
      <button onClick={stitch} disabled={!images.length} style={accentBtn}>合成</button>
      {output && (
        <div style={{ marginTop: 12, textAlign: "center" }}>
          <img src={output} alt="Stitched" style={{ maxWidth: "100%", maxHeight: 400, borderRadius: 6, border: "1px solid var(--line)" }} />
          <div style={{ marginTop: 8 }}>
            <a href={output} download="stitched.png" style={{ ...accentBtn, textDecoration: "none", display: "inline-block", fontSize: 12 }}>下载 PNG</a>
          </div>
        </div>
      )}
    </div>
  );
}

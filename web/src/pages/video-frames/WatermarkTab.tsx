import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";

const cardBg: React.CSSProperties = { background: "var(--bg-1)", borderRadius: 8, border: "1px solid var(--line)" };
const accentBtn: React.CSSProperties = {
  background: "var(--acc)", color: "#fff", border: "none", borderRadius: 6,
  padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer",
};
const secondaryBtn: React.CSSProperties = {
  background: "var(--bg-3)", color: "var(--txt-1)", border: "1px solid var(--line)",
  borderRadius: 6, padding: "6px 12px", fontSize: 12, cursor: "pointer",
};

export function WatermarkTab() {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!jobId || status === "completed" || status === "failed") return;
    const timer = setInterval(async () => {
      try {
        const j = await api.getWatermarkJob(jobId);
        setStatus(j.status);
        setProgress(j.progress ?? 0);
        if (j.error) setError(j.error.message || "Error");
      } catch {}
    }, 1000);
    return () => clearInterval(timer);
  }, [jobId, status]);

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true); setError(null);
    try {
      const res = await api.createWatermarkJob(file);
      setJobId(res.job_id); setStatus(res.status);
    } catch (e: any) { setError(e.message); }
    setUploading(false);
  };

  return (
    <div style={{ maxWidth: 640 }}>
      {/* 上传区 */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault(); setDragOver(false);
          const f = e.dataTransfer.files[0]; if (f) setFile(f);
        }}
        onClick={() => document.getElementById("vf-watermark-file")?.click()}
        style={{ ...cardBg, padding: 32, textAlign: "center", cursor: "pointer",
          borderColor: dragOver ? "var(--acc)" : "var(--line)", marginBottom: 16 }}
      >
        <input
          id="vf-watermark-file"
          type="file"
          accept="video/*"
          style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); }}
        />
        {file ? (
          <div>
            <div style={{ fontSize: 14, color: "var(--txt-1)", fontWeight: 600 }}>{file.name}</div>
            <div style={{ fontSize: 11, color: "var(--txt-3)", marginTop: 4 }}>
              {(file.size / 1024 / 1024).toFixed(1)} MB
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); setFile(null); setJobId(null); setStatus(""); setProgress(0); }}
              style={{ ...secondaryBtn, marginTop: 8, fontSize: 11 }}
            >
              更换文件
            </button>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🛡</div>
            <div style={{ fontSize: 13, color: "var(--txt-2)" }}>{t("videoFrames.watermark.dropTitle")}</div>
            <div style={{ fontSize: 11, color: "var(--txt-3)", marginTop: 4 }}>{t("videoFrames.watermark.dropHint")}</div>
          </div>
        )}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!file || uploading || status === "processing"}
        style={{ ...accentBtn, width: "100%", opacity: (!file || uploading) ? 0.5 : 1 }}
      >
        {uploading ? "上传中..." : status === "processing" ? t("videoFrames.watermark.processing") : t("videoFrames.watermark.submit")}
      </button>

      {error && (
        <div style={{ marginTop: 16, ...cardBg, padding: 12, borderColor: "#ef4444", color: "#ef4444", fontSize: 12 }}>
          {error}
        </div>
      )}

      {status === "processing" && (
        <div style={{ marginTop: 16, ...cardBg, padding: 16 }}>
          <div style={{ fontSize: 12, color: "var(--txt-2)", marginBottom: 8 }}>
            {t("videoFrames.watermark.progress", { cur: Math.round(progress / 100 * 30) || 0, total: 30 })}
          </div>
          <div style={{ height: 6, background: "var(--bg-0)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{
              height: "100%", width: `${Math.min(progress, 100)}%`,
              background: "var(--acc)", borderRadius: 3, transition: "width 0.3s",
            }} />
          </div>
        </div>
      )}

      {status === "completed" && jobId && (
        <div style={{ marginTop: 16, ...cardBg, padding: 16 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: "var(--acc)", marginBottom: 8 }}>
            {t("videoFrames.watermark.completed")}
          </div>
          <div style={{ fontSize: 12, color: "var(--txt-2)", marginBottom: 12 }}>
            水印已通过边缘检测 + TELEA 修复算法去除
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <a
              href={api.getWatermarkResultUrl(jobId)}
              download
              style={{ ...accentBtn, textDecoration: "none", display: "inline-block", fontSize: 12 }}
            >
              {t("videoFrames.watermark.download")}
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

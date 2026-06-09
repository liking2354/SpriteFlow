import { useState, useEffect, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { VFProbeResponse, VFJobResponse } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";

type Step = 1 | 2 | 3;

function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
function fmtRes(w: number, h: number): string { return `${w} × ${h}`; }

/* ===== Stepper ===== */
function Stepper({ step, onJump, canStep2, canStep3 }: {
  step: Step; onJump: (s: Step) => void; canStep2: boolean; canStep3: boolean;
}) {
  const { t } = useTranslation();
  const items: { id: Step; label: string; hint: string; enabled: boolean }[] = [
    { id: 1, label: t("videoFrames.new.stepSource"), hint: t("videoFrames.new.stepHintSource"), enabled: true },
    { id: 2, label: t("videoFrames.new.stepCrop"), hint: t("videoFrames.new.stepHintCrop"), enabled: canStep2 },
    { id: 3, label: t("videoFrames.new.stepExport"), hint: t("videoFrames.new.stepHintExport"), enabled: canStep3 },
  ];
  return (
    <div className="rounded-l border border-line bg-bg-2 p-3">
      <div className="grid grid-cols-3 gap-2">
        {items.map((it, i) => {
          const active = it.id === step, done = it.id < step, clickable = it.enabled;
          return (
            <button key={it.id} disabled={!clickable} onClick={() => clickable && onJump(it.id)}
              className={`relative text-left rounded-s border px-3 py-2.5 transition-colors ${
                active ? "border-[var(--acc)] bg-[var(--acc)]/10"
                : done ? "border-line bg-bg-3 hover:border-[var(--acc)]/60"
                : clickable ? "border-line bg-bg-3 hover:border-[var(--acc)]/60"
                : "border-line/40 bg-bg-3/40 cursor-not-allowed"}`}>
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 grid place-items-center rounded-full text-[11px] font-mono ${
                  active ? "bg-[var(--acc)] text-white"
                  : done ? "bg-[var(--green)]/80 text-white"
                  : "bg-bg-0 text-txt-3 border border-line"}`}>
                  {done ? "✓" : i + 1}
                </span>
                <span className={`text-[12.5px] font-medium ${active ? "text-txt-0" : clickable ? "text-txt-1" : "text-txt-3"}`}>
                  {it.label}
                </span>
              </div>
              <div className="mt-1 text-[10.5px] text-txt-3 line-clamp-1">{it.hint}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ===== VideoPlayer ===== */
function VideoPlayer({ videoUrl, probe, startSec, endSec, onStartChange, onEndChange }: {
  videoUrl: string; probe: VFProbeResponse;
  startSec: number; endSec: number;
  onStartChange: (v: number) => void; onEndChange: (v: number) => void;
}) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(probe.duration);
  const [seeking, setSeeking] = useState(false);
  const wasPlayingRef = useRef(false);

  useEffect(() => {
    const v = videoRef.current; if (!v) return;
    const h = () => { if (!seeking) setCurrentTime(v.currentTime); };
    const d = () => setDuration(v.duration);
    const e = () => setPlaying(false);
    v.addEventListener("timeupdate", h); v.addEventListener("loadedmetadata", d); v.addEventListener("ended", e);
    return () => { v.removeEventListener("timeupdate", h); v.removeEventListener("loadedmetadata", d); v.removeEventListener("ended", e); };
  }, [seeking]);

  const togglePlay = () => { const v = videoRef.current; if (!v) return; if (v.paused) { v.play(); setPlaying(true); } else { v.pause(); setPlaying(false); } };
  const toggleMute = () => { const v = videoRef.current; if (!v) return; v.muted = !v.muted; setMuted(!muted); };
  const seekStart = () => { wasPlayingRef.current = playing; if (playing) { videoRef.current?.pause(); setPlaying(false); } setSeeking(true); };
  const seekEnd = () => { setSeeking(false); const v = videoRef.current; if (!v) return; v.currentTime = currentTime; if (wasPlayingRef.current) { v.play(); setPlaying(true); } };

  return (
    <div>
      <div className="relative bg-black rounded-s overflow-hidden" style={{ aspectRatio: "16/9", maxHeight: 320 }}>
        <video ref={videoRef} src={videoUrl} muted={muted} className="w-full h-full object-contain cursor-pointer" onClick={togglePlay} />
        {!playing && (
          <button onClick={togglePlay} className="absolute inset-0 flex items-center justify-center bg-black/30">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="white" opacity={0.85}><path d="M8 5v14l11-7z" /></svg>
          </button>
        )}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={togglePlay} className="w-7 h-7 grid place-items-center rounded-s text-txt-1 hover:text-txt-0 hover:bg-bg-3">
          {playing
            ? <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
            : <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>}
        </button>
        <button onClick={toggleMute} className="w-7 h-7 grid place-items-center rounded-s text-txt-1 hover:text-txt-0 hover:bg-bg-3">
          {muted
            ? <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" /></svg>
            : <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" /></svg>}
        </button>
        <span className="text-[10px] text-txt-2 font-mono min-w-[68px]">{fmtDuration(currentTime)} / {fmtDuration(duration)}</span>
        <input type="range" min={0} max={duration || 1} step={0.01} value={currentTime}
          onMouseDown={seekStart} onTouchStart={seekStart} onChange={(e) => setCurrentTime(Number(e.target.value))}
          onMouseUp={seekEnd} onTouchEnd={seekEnd} className="flex-1 h-1 accent-[var(--acc)] cursor-pointer" />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded-s bg-bg-2 border border-line p-2.5"><div className="text-txt-3 mb-0.5">{t("videoFrames.new.duration")}</div><div className="text-txt-0 font-mono font-semibold">{fmtDuration(probe.duration)}</div></div>
        <div className="rounded-s bg-bg-2 border border-line p-2.5"><div className="text-txt-3 mb-0.5">{t("videoFrames.new.resolution")}</div><div className="text-txt-0 font-mono font-semibold">{fmtRes(probe.width, probe.height)}</div></div>
        <div className="rounded-s bg-bg-2 border border-line p-2.5"><div className="text-txt-3 mb-0.5">{t("videoFrames.new.originalFps")}</div><div className="text-txt-0 font-mono font-semibold">{probe.original_fps.toFixed(1)}</div></div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div className="flex items-center justify-between mb-1"><span className="text-[11px] text-txt-2">{t("videoFrames.new.startTime")}</span><span className="text-[10.5px] text-txt-3 font-mono">{startSec.toFixed(1)}s</span></div>
          <input type="range" min={0} max={probe.duration} step={0.1} value={Math.min(startSec, endSec - 0.1)} onChange={(e) => onStartChange(Number(e.target.value))} className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1"><span className="text-[11px] text-txt-2">{t("videoFrames.new.endTime")}</span><span className="text-[10.5px] text-txt-3 font-mono">{endSec.toFixed(1)}s</span></div>
          <input type="range" min={0} max={probe.duration} step={0.1} value={Math.max(endSec, startSec + 0.1)} onChange={(e) => onEndChange(Number(e.target.value))} className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
        </div>
      </div>
    </div>
  );
}

/* ===== Main Component ===== */
export function ExtractTab() {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>(1);
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [probe, setProbe] = useState<VFProbeResponse | null>(null);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [fps, setFps] = useState(12);
  const [startSec, setStartSec] = useState(0);
  const [endSec, setEndSec] = useState(0);
  const [maxFrames, setMaxFrames] = useState(300);
  const [spacing, setSpacing] = useState(4);
  const [layoutMode, setLayoutMode] = useState("auto_square");
  const [columns, setColumns] = useState(8);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<VFJobResponse["result"]>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [spriteUrl, setSpriteUrl] = useState<string | null>(null);
  const [crop, setCrop] = useState({ left: 0, top: 0, right: 0, bottom: 0 });
  const [cropping, setCropping] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(async (f: File) => {
    setFile(f); setProbe(null); setProbeError(null); setJobId(null); setResult(null); setSpriteUrl(null); setStep(1); setStatus(""); setProgress(0); setError(null);
    setVideoUrl(URL.createObjectURL(f));
    setProbing(true);
    try { const info = await api.probeVideo(f); setProbe(info); setEndSec(info.duration); setStartSec(0); } catch (e: any) { setProbeError(e.message); }
    setProbing(false);
  }, []);

  const estimatedFrames = probe ? Math.min(maxFrames, Math.floor((endSec - startSec) * fps)) : 0;

  const handleSubmit = async () => {
    if (!file) return; setSubmitting(true); setError(null); setResult(null); setSpriteUrl(null);
    try {
      const res = await api.createVFJob(file, { fps, max_frames: maxFrames, start_sec: startSec, end_sec: endSec, spacing, layout_mode: layoutMode, columns });
      setJobId(res.job_id); setStatus(res.status);
    } catch (e: any) { setError(e.message); }
    setSubmitting(false);
  };

  useEffect(() => {
    if (!jobId || status === "completed" || status === "failed") return;
    const timer = setInterval(async () => {
      try { const j = await api.getVFJob(jobId); setStatus(j.status); setProgress(j.progress); if (j.result) setResult(j.result); if (j.error) setError(j.error.message || "Error"); } catch {}
    }, 800);
    return () => clearInterval(timer);
  }, [jobId, status]);

  useEffect(() => { if (status === "completed" && result) { setSpriteUrl(api.getVFResultUrl(jobId!, "png")); setStep(2); } }, [status, result, jobId]);

  const handleCrop = async () => {
    if (!jobId) return; setCropping(true);
    try {
      const res = await api.cropVFJob(jobId, crop);
      setResult((prev) => prev ? { ...prev, frame_size: res.frame_size, sheet_size: res.sheet_size } : prev);
      setSpriteUrl(api.getVFResultUrl(jobId, "png") + "&t=" + Date.now());
    } catch (e: any) { setError(e.message); }
    setCropping(false);
  };

  const handleBackToStep1 = () => { setStep(1); setResult(null); setSpriteUrl(null); setJobId(null); setStatus(""); setProgress(0); };

  return (
    <div className="space-y-4">
      <Stepper step={step} onJump={(s) => { if (s <= step || (s === 2 && status === "completed") || (s === 3 && status === "completed")) setStep(s as Step); }} canStep2={status === "completed"} canStep3={status === "completed"} />

      {/* Step 1 */}
      {step === 1 && (
        <div className="grid grid-cols-[minmax(340px,420px)_1fr] gap-5">
          <div className="space-y-4">
            <Card title={t("videoFrames.new.sourceTitle")} subtitle={t("videoFrames.new.sourceHint")}>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
                onClick={() => document.getElementById("vf-extract-file")?.click()}
                className={`rounded-s border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${dragOver ? "border-[var(--acc)] bg-[var(--acc)]/5" : "border-line hover:border-[var(--acc)]/50"}`}>
                <input id="vf-extract-file" type="file" accept="video/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
                {file ? (
                  <div>
                    <div className="text-[14px] text-txt-0 font-semibold">{file.name}</div>
                    <div className="text-[11px] text-txt-3 mt-1">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
                    {probing && <div className="mt-2 text-[11px] text-txt-2">探测中...</div>}
                    {probeError && <div className="mt-2 text-[11px] text-red-400">{probeError}</div>}
                    <button onClick={(e) => { e.stopPropagation(); setFile(null); setVideoUrl(null); setProbe(null); }} className="mt-3 text-[11px] text-txt-2 hover:text-txt-0 underline">{t("videoFrames.new.changeFile")}</button>
                  </div>
                ) : (
                  <div><div className="text-[28px] mb-2">🎬</div><div className="text-[13px] text-txt-2">{t("videoFrames.new.dropTitle")}</div><div className="text-[11px] text-txt-3 mt-1">{t("videoFrames.new.dropHint")}</div></div>
                )}
              </div>
              {probe && (
                <div className="mt-5 border-t border-line pt-4">
                  <div className="text-[12px] font-semibold text-txt-0 mb-3">{t("videoFrames.new.exportParams")}</div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("videoFrames.new.fps")}><TextInput type="number" value={fps} min={1} max={60} onChange={(e) => setFps(Number(e.target.value))} /></Field>
                    <Field label={t("videoFrames.new.maxFrames")}><TextInput type="number" value={maxFrames} min={1} max={999} onChange={(e) => setMaxFrames(Number(e.target.value))} /></Field>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("videoFrames.new.startTimeShort")} hint={`${startSec.toFixed(1)} s`}><TextInput type="number" value={startSec} min={0} max={probe.duration} step={0.1} onChange={(e) => setStartSec(Number(e.target.value))} /></Field>
                    <Field label={t("videoFrames.new.endTimeShort")} hint={`${endSec.toFixed(1)} s`}><TextInput type="number" value={endSec} min={0} max={probe.duration} step={0.1} onChange={(e) => setEndSec(Number(e.target.value))} /></Field>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("videoFrames.extract.layoutMode")}>
                      <select value={layoutMode} onChange={(e) => setLayoutMode(e.target.value)} className="w-full px-3 h-9 bg-bg-0 border border-line rounded-s text-[12px] text-txt-0 font-mono focus:border-[var(--acc)] transition-all cursor-pointer appearance-none">
                        <option value="auto_square">{t("videoFrames.extract.layoutAuto")}</option>
                        <option value="fixed_columns">{t("videoFrames.extract.layoutFixed")}</option>
                      </select>
                    </Field>
                    {layoutMode === "fixed_columns" ? <Field label={t("videoFrames.extract.columns")}><TextInput type="number" value={columns} min={1} max={64} onChange={(e) => setColumns(Number(e.target.value))} /></Field> : <div />}
                    <Field label={t("videoFrames.extract.spacing")}><TextInput type="number" value={spacing} min={0} max={64} onChange={(e) => setSpacing(Number(e.target.value))} /></Field>
                  </div>
                  <div className="mt-3 rounded-s bg-[var(--acc)]/10 border border-[var(--acc)]/30 p-3">
                    <div className="flex items-center justify-between"><span className="text-[11px] text-txt-2">{t("videoFrames.new.estimatedFrames")}</span><span className="text-[14px] font-bold text-[var(--acc)] font-mono">{estimatedFrames}</span></div>
                    <div className="mt-0.5 text-[10px] text-txt-3">= min({t("videoFrames.new.maxFrames")}, ({endSec.toFixed(1)} - {startSec.toFixed(1)}) × {fps})</div>
                  </div>
                </div>
              )}
              {probe && <Button onClick={handleSubmit} disabled={!file || submitting || status === "processing"} loading={submitting || status === "processing"} className="w-full mt-4">{submitting ? t("videoFrames.extract.uploading") : status === "processing" ? `${t("videoFrames.extract.processing")} ${progress}%` : t("videoFrames.extract.submit")}</Button>}
              {status === "processing" && <div className="mt-3"><div className="h-1.5 bg-bg-0 rounded-full overflow-hidden"><div className="h-full bg-[var(--acc)] rounded-full transition-all duration-300" style={{ width: `${progress}%` }} /></div></div>}
              {error && <div className="mt-3 text-[12px] text-red-400 bg-red-400/5 border border-red-400/20 rounded-s p-2.5">{error}</div>}
            </Card>
          </div>
          <div>
            {videoUrl && probe ? (
              <Card title={t("videoFrames.new.videoPreview")} subtitle={probe.filename}>
                <VideoPlayer videoUrl={videoUrl} probe={probe} startSec={startSec} endSec={endSec} onStartChange={setStartSec} onEndChange={setEndSec} />
              </Card>
            ) : (
              <Card title={t("videoFrames.new.videoPreview")} subtitle={t("videoFrames.new.uploadFirst")}>
                <div className="flex items-center justify-center h-[320px] text-[13px] text-txt-3">{t("videoFrames.new.uploadFirst")}</div>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <div className="grid grid-cols-[1fr_minmax(340px,380px)] gap-5">
          <Card title={t("videoFrames.new.spritePreview")}>
            {spriteUrl && (
              <div className="text-center">
                <img src={spriteUrl} alt="Sprite Sheet" className="max-w-full max-h-[520px] rounded-s" style={{ imageRendering: "pixelated" }} />
                {result?.frame_size && <div className="mt-3 flex items-center justify-center gap-4 text-[11px] text-txt-3 font-mono">
                  <span>{t("videoFrames.new.frameSize")}: {result.frame_size.w}×{result.frame_size.h}</span>
                  <span>{t("videoFrames.new.sheetSize")}: {result.sheet_size?.w ?? "?"}×{result.sheet_size?.h ?? "?"}</span>
                  <span>{t("videoFrames.new.frameCount")}: {result.frame_count ?? 0}</span>
                </div>}
              </div>
            )}
          </Card>
          <div className="space-y-4">
            <Card title={t("videoFrames.new.cropTitle")} subtitle={t("videoFrames.new.cropHint")}>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("videoFrames.new.cropLeft")}><TextInput type="number" value={crop.left} min={0} onChange={(e) => setCrop((c) => ({ ...c, left: Number(e.target.value) }))} /></Field>
                <Field label={t("videoFrames.new.cropRight")}><TextInput type="number" value={crop.right} min={0} onChange={(e) => setCrop((c) => ({ ...c, right: Number(e.target.value) }))} /></Field>
                <Field label={t("videoFrames.new.cropTop")}><TextInput type="number" value={crop.top} min={0} onChange={(e) => setCrop((c) => ({ ...c, top: Number(e.target.value) }))} /></Field>
                <Field label={t("videoFrames.new.cropBottom")}><TextInput type="number" value={crop.bottom} min={0} onChange={(e) => setCrop((c) => ({ ...c, bottom: Number(e.target.value) }))} /></Field>
              </div>
              {result?.frame_size && <div className="mt-3 text-[10.5px] text-txt-3 font-mono">{t("videoFrames.new.cropResult")}: {Math.max(0, result.frame_size.w - crop.left - crop.right)} × {Math.max(0, result.frame_size.h - crop.top - crop.bottom)}</div>}
              <Button onClick={handleCrop} loading={cropping} size="sm" className="w-full mt-4">{t("videoFrames.new.applyCrop")}</Button>
              {error && <div className="mt-3 text-[12px] text-red-400 bg-red-400/5 border border-red-400/20 rounded-s p-2.5">{error}</div>}
            </Card>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleBackToStep1}>{t("videoFrames.new.backAdjust")}</Button>
              <Button variant="primary" size="sm" className="flex-1" onClick={() => setStep(3)}>{t("videoFrames.new.toExport")}</Button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div className="grid grid-cols-[1fr_minmax(340px,380px)] gap-5">
          <Card title={t("videoFrames.new.exportPreview")}>
            {spriteUrl && <div className="text-center"><img src={spriteUrl} alt="Sprite Sheet" className="max-w-full max-h-[400px] rounded-s" style={{ imageRendering: "pixelated" }} /></div>}
          </Card>
          <div className="space-y-4">
            <Card title={t("videoFrames.new.exportTitle")} subtitle={t("videoFrames.new.exportHint")}>
              <div className="space-y-3">
                <a href={api.getVFResultUrl(jobId!, "png")} download className="block"><Button variant="primary" className="w-full">{t("videoFrames.extract.downloadPng")}</Button></a>
                <a href={api.getVFResultUrl(jobId!, "zip")} download className="block"><Button variant="outline" className="w-full">{t("videoFrames.extract.downloadZip")}</Button></a>
              </div>
            </Card>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setStep(2)}>{t("spritesheet.prev")}</Button>
              <Button variant="ghost" size="sm" className="flex-1" onClick={handleBackToStep1}>{t("videoFrames.new.reExtract")}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { VFProbeResponse, VFJobResponse } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { loadImage, exportFramesZip, exportFramesGif, recombineFrames, downloadBlob, flipFrameH, shiftFrame } from "@/lib/spritesheet";
import type { Frame } from "@/lib/spritesheet";

type Step = 1 | 2 | 3;
type ProcessingMode = "pixel" | "smooth";

interface FrameInfo { name: string; url: string; index: number; selected: boolean; w?: number; h?: number; }
const CELL_PRESETS = [0, 32, 48, 64, 96, 128, 192, 256, 384, 512];

function fmtDuration(sec: number): string { const m = Math.floor(sec / 60); const s = Math.floor(sec % 60); return `${m}:${String(s).padStart(2, "0")}`; }
function fmtRes(w: number, h: number): string { return `${w} × ${h}`; }
async function urlToBlob(url: string): Promise<Blob> { const r = await fetch(url); return r.blob(); }
async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve) => { const r = new FileReader(); r.onloadend = () => resolve(r.result as string); r.readAsDataURL(blob); });
}

/* ===== Shared: Perceptual Hash Vector Computation ===== */
const THUMB = 32;
const THUMB_PX = THUMB * THUMB;

function computeFrameVectors(frameUrls: string[]): Promise<{ vectors: Float64Array[]; validIndices: number[] }> {
  return new Promise((resolve) => {
    const n = frameUrls.length;
    const imgs: (HTMLImageElement | null)[] = [];
    let loaded = 0;
    frameUrls.forEach((url, idx) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => { imgs[idx] = img; loaded++; if (loaded === n) process(); };
      img.onerror = () => { loaded++; if (loaded === n) process(); };
      img.src = url;
    });
    function process() {
      const c = document.createElement("canvas");
      c.width = c.height = THUMB;
      const ctx = c.getContext("2d")!;
      const vectors: Float64Array[] = [];
      const validIndices: number[] = [];
      frameUrls.forEach((_, i) => {
        const img = imgs[i];
        if (!img) return;
        ctx.clearRect(0, 0, THUMB, THUMB);
        ctx.drawImage(img, 0, 0, THUMB, THUMB);
        const d = ctx.getImageData(0, 0, THUMB, THUMB).data;
        const v = new Float64Array(THUMB_PX);
        let mean = 0;
        for (let j = 0; j < THUMB_PX; j++) {
          v[j] = 0.299 * d[j * 4] + 0.587 * d[j * 4 + 1] + 0.114 * d[j * 4 + 2];
          mean += v[j];
        }
        mean /= THUMB_PX;
        for (let j = 0; j < THUMB_PX; j++) v[j] -= mean;
        vectors.push(v);
        validIndices.push(i);
      });
      resolve({ vectors, validIndices });
    }
  });
}

function vectorDiff(a: Float64Array, b: Float64Array): number {
  let sum = 0;
  for (let k = 0; k < THUMB_PX; k++) sum += Math.abs(a[k] - b[k]);
  return sum / (THUMB_PX * 255);
}

/* ===== Diversity-based Key Frame Selection ===== */
function diversitySelectFrames(frameUrls: string[], target: number): Promise<number[]> {
  if (frameUrls.length <= target) return Promise.resolve(Array.from({ length: frameUrls.length }, (_, i) => i));
  return computeFrameVectors(frameUrls).then(({ vectors, validIndices }) => {
    if (vectors.length <= target) return validIndices;
    const m = vectors.length;
    const selected: number[] = [0];
    const minDist = new Float64Array(m).fill(Infinity);
    for (let i = 1; i < m; i++) minDist[i] = vectorDiff(vectors[0], vectors[i]);
    while (selected.length < target) {
      let best = -1, bestDist = -1;
      for (let i = 0; i < m; i++) {
        if (!selected.includes(i) && minDist[i] > bestDist) { bestDist = minDist[i]; best = i; }
      }
      if (best < 0) break;
      selected.push(best);
      for (let i = 0; i < m; i++) {
        if (!selected.includes(i)) {
          const d2 = vectorDiff(vectors[best], vectors[i]);
          if (d2 < minDist[i]) minDist[i] = d2;
        }
      }
    }
    return selected.map(s => validIndices[s]).sort((a, b) => a - b);
  });
}

/* ===== Cycle Detection Sampling (autocorrelation on frame differences) ===== */
function detectCyclePeriod(diffs: number[]): number | null {
  const N = diffs.length;
  if (N < 6) return null;
  // normalize (subtract mean)
  const mean = diffs.reduce((a, b) => a + b, 0) / N;
  const norm = diffs.map(d => d - mean);
  // autocorrelation for lags 2..N/2
  const maxLag = Math.floor(N / 2);
  const autoCorr: number[] = [];
  for (let lag = 2; lag <= maxLag; lag++) {
    let sum = 0;
    for (let i = 0; i < N - lag; i++) sum += norm[i] * norm[i + lag];
    autoCorr.push(sum / (N - lag));
  }
  // find first significant positive peak
  const maxCorr = Math.max(...autoCorr);
  if (maxCorr <= 0) return null;
  for (let i = 1; i < autoCorr.length - 1; i++) {
    if (autoCorr[i] > 0 && autoCorr[i] > autoCorr[i - 1] * 0.9 && autoCorr[i] >= autoCorr[i + 1]) {
      if (autoCorr[i] > maxCorr * 0.35) return i + 2; // lag = i+2
    }
  }
  return null;
}

function cycleDetectAndSample(frameUrls: string[], target: number): Promise<{ indices: number[]; cycleLen: number | null }> {
  const n = frameUrls.length;
  if (n <= target) return Promise.resolve({ indices: Array.from({ length: n }, (_, i) => i), cycleLen: null });
  return computeFrameVectors(frameUrls).then(({ vectors, validIndices }) => {
    if (vectors.length <= target) return { indices: validIndices, cycleLen: null };
    // compute frame-to-frame perceptual differences
    const diffs: number[] = [];
    for (let i = 0; i < vectors.length - 1; i++) {
      diffs.push(vectorDiff(vectors[i], vectors[i + 1]));
    }
    // smooth diffs with 3-frame moving average
    const smoothed: number[] = [];
    for (let i = 0; i < diffs.length; i++) {
      let sum = diffs[i], cnt = 1;
      if (i > 0) { sum += diffs[i - 1]; cnt++; }
      if (i < diffs.length - 1) { sum += diffs[i + 1]; cnt++; }
      smoothed.push(sum / cnt);
    }
    const cycleLen = detectCyclePeriod(smoothed);
    let indices: number[];
    if (cycleLen && cycleLen >= 4 && cycleLen <= n / 2) {
      // find "start frame" — the frame with minimum diff in first cycle range
      let startIdx = 0, minVal = Infinity;
      for (let i = 0; i < cycleLen && i < smoothed.length; i++) {
        if (smoothed[i] < minVal) { minVal = smoothed[i]; startIdx = i; }
      }
      // pick target frames evenly within one cycle, starting from startIdx
      indices = [];
      const endIdx = Math.min(startIdx + cycleLen, validIndices.length);
      const rangeLen = endIdx - startIdx;
      for (let i = 0; i < target; i++) {
        const pos = startIdx + Math.round(i * (rangeLen - 1) / (target - 1));
        indices.push(validIndices[Math.min(pos, validIndices.length - 1)]);
      }
    } else {
      // fallback: uniform sampling
      indices = [];
      for (let i = 0; i < target; i++) {
        indices.push(validIndices[Math.round(i * (validIndices.length - 1) / (target - 1))]);
      }
    }
    return { indices, cycleLen };
  });
}

/* ===== Stepper ===== */
function VFStepper({ step, onJump, canStep2, canStep3 }: { step: Step; onJump: (s: Step) => void; canStep2: boolean; canStep3: boolean }) {
  const { t } = useTranslation();
  const items = [
    { id: 1, label: t("videoFrames.new.stepSource"), hint: t("videoFrames.new.stepHintSource"), enabled: true },
    { id: 2, label: t("videoFrames.new.stepCrop"), hint: t("videoFrames.new.stepHintCrop"), enabled: canStep2 },
    { id: 3, label: t("videoFrames.new.stepExport"), hint: t("videoFrames.new.stepHintExport"), enabled: canStep3 },
  ];
  return (
    <div className="rounded-l border border-line bg-bg-2 p-3">
      <div className="grid grid-cols-3 gap-2">
        {items.map((it, i) => {
          const active = it.id === step;
          const done = it.id < step;
          const click = it.enabled;
          return (
            <button key={it.id} disabled={!click} onClick={() => click && onJump(it.id as Step)}
              className={`relative text-left rounded-s border px-3 py-2.5 transition-colors ${
                active ? "border-[var(--acc)] bg-[var(--acc)]/10"
                : done ? "border-line bg-bg-3 hover:border-[var(--acc)]/60"
                : click ? "border-line bg-bg-3 hover:border-[var(--acc)]/60"
                : "border-line/40 bg-bg-3/40 cursor-not-allowed"}`}>
              <div className="flex items-center gap-2">
                <span className={`w-5 h-5 grid place-items-center rounded-full text-[11px] font-mono ${
                  active ? "bg-[var(--acc)] text-white"
                  : done ? "bg-[var(--green)]/80 text-white"
                  : "bg-bg-0 text-txt-3 border border-line"}`}>
                  {done ? "\u2713" : i + 1}
                </span>
                <span className={`text-[12.5px] font-medium ${active ? "text-txt-0" : click ? "text-txt-1" : "text-txt-3"}`}>
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

/* ===== VideoPlayer (with crop overlay aligned to actual video content) ===== */
function VideoPlayer({ videoUrl, probe, startSec, endSec, onStartChange, onEndChange, cropHPct = 0, cropVPct = 0 }: {
  videoUrl: string; probe: VFProbeResponse; startSec: number; endSec: number;
  onStartChange: (v: number) => void; onEndChange: (v: number) => void;
  cropHPct?: number; cropVPct?: number;
}) {
  const { t } = useTranslation();
  const vr = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [ct, setCt] = useState(0);
  const [dur, setDur] = useState(probe.duration);
  const [seeking, setSeeking] = useState(false);
  const wr = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerW, setContainerW] = useState(0);
  const [containerH, setContainerH] = useState(0);

  // track container size for letterbox calculation
  useEffect(() => {
    const el = containerRef.current; if (!el) return;
    const measure = () => { setContainerW(el.clientWidth); setContainerH(el.clientHeight); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // compute video display area within object-contain container
  const videoAspect = probe.width / probe.height;
  const containerAspect = containerW > 0 && containerH > 0 ? containerW / containerH : 16 / 9;
  let videoLeftPct = 0, videoTopPct = 0, videoWPct = 100, videoHPct = 100;
  if (containerW > 0 && containerH > 0) {
    if (videoAspect < containerAspect) {
      // video is taller → fills height, horizontal letterbox
      videoHPct = 100;
      videoWPct = (videoAspect / containerAspect) * 100;
      videoLeftPct = (100 - videoWPct) / 2;
      videoTopPct = 0;
    } else {
      // video is wider → fills width, vertical letterbox
      videoWPct = 100;
      videoHPct = (containerAspect / videoAspect) * 100;
      videoTopPct = (100 - videoHPct) / 2;
      videoLeftPct = 0;
    }
  }

  // crop bars positioned relative to video area, not container
  const cropLeftCSS = videoLeftPct + videoWPct * cropHPct / 100;
  const cropRightCSS = 100 - videoLeftPct - videoWPct * cropHPct / 100;
  const cropTopCSS = videoTopPct + videoHPct * cropVPct / 100;
  const cropBottomCSS = 100 - videoTopPct - videoHPct * cropVPct / 100;

  useEffect(() => {
    const v = vr.current; if (!v) return;
    const h = () => { if (!seeking) setCt(v.currentTime); };
    const d = () => setDur(v.duration);
    const e = () => setPlaying(false);
    v.addEventListener("timeupdate", h);
    v.addEventListener("loadedmetadata", d);
    v.addEventListener("ended", e);
    return () => { v.removeEventListener("timeupdate", h); v.removeEventListener("loadedmetadata", d); v.removeEventListener("ended", e); };
  }, [seeking]);

  const tp = () => { const v = vr.current; if (!v) return; if (v.paused) { v.play(); setPlaying(true); } else { v.pause(); setPlaying(false); } };
  const tm = () => { const v = vr.current; if (!v) return; v.muted = !v.muted; setMuted(!muted); };
  const ss = () => { wr.current = playing; if (playing) { vr.current?.pause(); setPlaying(false); } setSeeking(true); };
  const se = () => { setSeeking(false); const v = vr.current; if (!v) return; v.currentTime = ct; if (wr.current) { v.play(); setPlaying(true); } };

  const hasCrop = cropHPct > 0 || cropVPct > 0;

  return (
    <div>
      <div ref={containerRef} className="relative bg-black rounded-s overflow-hidden" style={{ aspectRatio: "16/9", maxHeight: 320 }}>
        <video ref={vr} src={videoUrl} muted={muted} className="w-full h-full object-contain cursor-pointer" onClick={tp} />
        {hasCrop && (
          <div className="absolute inset-0 pointer-events-none z-10" style={{ overflow: "hidden" }}>
            {/* cropped regions: red diagonal-stripe overlay — makes it obvious what will be removed */}
            {/* top bar */}
            {cropVPct > 0 && (
              <div className="absolute top-0 left-0 right-0" style={{
                height: `${cropTopCSS}%`,
                background: "repeating-linear-gradient(-45deg, rgba(239,68,68,0.22), rgba(239,68,68,0.22) 5px, transparent 5px, transparent 9px)",
              }} />
            )}
            {/* bottom bar */}
            {cropVPct > 0 && (
              <div className="absolute bottom-0 left-0 right-0" style={{
                height: `${cropBottomCSS}%`,
                background: "repeating-linear-gradient(-45deg, rgba(239,68,68,0.22), rgba(239,68,68,0.22) 5px, transparent 5px, transparent 9px)",
              }} />
            )}
            {/* left bar */}
            {cropHPct > 0 && (
              <div className="absolute top-0 bottom-0 left-0" style={{
                width: `${cropLeftCSS}%`,
                background: "repeating-linear-gradient(-45deg, rgba(239,68,68,0.22), rgba(239,68,68,0.22) 5px, transparent 5px, transparent 9px)",
              }} />
            )}
            {/* right bar */}
            {cropHPct > 0 && (
              <div className="absolute top-0 bottom-0 right-0" style={{
                width: `${cropRightCSS}%`,
                background: "repeating-linear-gradient(-45deg, rgba(239,68,68,0.22), rgba(239,68,68,0.22) 5px, transparent 5px, transparent 9px)",
              }} />
            )}
            {/* dashed keep-area boundary with glow */}
            <div className="absolute border-2 border-dashed border-white/65 shadow-[0_0_10px_rgba(255,255,255,0.12)]"
              style={{ top: `${cropTopCSS}%`, bottom: `${cropBottomCSS}%`, left: `${cropLeftCSS}%`, right: `${cropRightCSS}%` }} />
            {/* four corner brackets — L-shaped white markers */}
            <div className="absolute w-3.5 h-3.5 border-t-2 border-l-2 border-white/90"
              style={{ top: `calc(${cropTopCSS}% + 1px)`, left: `calc(${cropLeftCSS}% + 1px)` }} />
            <div className="absolute w-3.5 h-3.5 border-t-2 border-r-2 border-white/90"
              style={{ top: `calc(${cropTopCSS}% + 1px)`, right: `calc(${cropRightCSS}% + 1px)` }} />
            <div className="absolute w-3.5 h-3.5 border-b-2 border-l-2 border-white/90"
              style={{ bottom: `calc(${cropBottomCSS}% + 1px)`, left: `calc(${cropLeftCSS}% + 1px)` }} />
            <div className="absolute w-3.5 h-3.5 border-b-2 border-r-2 border-white/90"
              style={{ bottom: `calc(${cropBottomCSS}% + 1px)`, right: `calc(${cropRightCSS}% + 1px)` }} />
          </div>
        )}
        {!playing && <button onClick={tp} className="absolute inset-0 flex items-center justify-center bg-black/30 z-20">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="white" opacity={0.85}><path d="M8 5v14l11-7z" /></svg>
        </button>}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={tp} className="w-7 h-7 grid place-items-center rounded-s text-txt-1 hover:text-txt-0 hover:bg-bg-3">
          {playing
            ? <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
            : <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>}
        </button>
        <button onClick={tm} className="w-7 h-7 grid place-items-center rounded-s text-txt-1 hover:text-txt-0 hover:bg-bg-3">
          {muted ? "\uD83D\uDD07" : "\uD83D\uDD0A"}
        </button>
        <span className="text-[10px] text-txt-2 font-mono min-w-[68px]">{fmtDuration(ct)}/{fmtDuration(dur)}</span>
        <input type="range" min={0} max={dur || 1} step={0.01} value={ct}
          onMouseDown={ss} onTouchStart={ss}
          onChange={e => setCt(Number(e.target.value))}
          onMouseUp={se} onTouchEnd={se}
          className="flex-1 h-1 accent-[var(--acc)] cursor-pointer" />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <div className="rounded-s bg-bg-2 border border-line p-2.5">
          <div className="text-txt-3 mb-0.5">{t("videoFrames.new.duration")}</div>
          <div className="text-txt-0 font-mono font-semibold">{fmtDuration(probe.duration)}</div>
        </div>
        <div className="rounded-s bg-bg-2 border border-line p-2.5">
          <div className="text-txt-3 mb-0.5">{t("videoFrames.new.resolution")}</div>
          <div className="text-txt-0 font-mono font-semibold">{fmtRes(probe.width, probe.height)}</div>
        </div>
        <div className="rounded-s bg-bg-2 border border-line p-2.5">
          <div className="text-txt-3 mb-0.5">{t("videoFrames.new.originalFps")}</div>
          <div className="text-txt-0 font-mono font-semibold">{probe.original_fps.toFixed(1)}</div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-txt-2">{t("videoFrames.new.startTime")}</span>
            <span className="text-[10.5px] text-txt-3 font-mono">{startSec.toFixed(1)}s</span>
          </div>
          <input type="range" min={0} max={probe.duration} step={0.1}
            value={Math.min(startSec, endSec - 0.1)}
            onChange={e => onStartChange(Number(e.target.value))}
            className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-txt-2">{t("videoFrames.new.endTime")}</span>
            <span className="text-[10.5px] text-txt-3 font-mono">{endSec.toFixed(1)}s</span>
          </div>
          <input type="range" min={0} max={probe.duration} step={0.1}
            value={Math.max(endSec, startSec + 0.1)}
            onChange={e => onEndChange(Number(e.target.value))}
            className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
        </div>
      </div>
    </div>
  );
}


/* ===== Shared drawFrame helper for AnimPreview ===== */
function drawFrame(ctx: CanvasRenderingContext2D, cw: number, ch: number, src: HTMLCanvasElement, checkerboard: boolean, crosshair: boolean, smooth: boolean) {
  ctx.imageSmoothingEnabled = smooth;
  ctx.clearRect(0, 0, cw, ch);

  // checkerboard behind image — visible through transparent pixels (e.g. after AI matte)
  if (checkerboard) {
    const sq = 8;
    for (let y = 0; y < ch; y += sq) {
      for (let x = 0; x < cw; x += sq) {
        ctx.fillStyle = ((Math.floor(x / sq) + Math.floor(y / sq)) % 2 === 0) ? "#3a3a5a" : "#2a2a3a";
        ctx.fillRect(x, y, sq, sq);
      }
    }
  }
  ctx.drawImage(src, 0, 0, cw, ch);

  // crosshair on top — adaptive lineWidth so it remains visible after CSS downscale
  if (crosshair) {
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.lineWidth = Math.max(2, Math.ceil(Math.min(cw, ch) / 80));
    ctx.setLineDash([8, 4]);
    ctx.beginPath();
    ctx.moveTo(cw / 2, 0); ctx.lineTo(cw / 2, ch);
    ctx.moveTo(0, ch / 2); ctx.lineTo(cw, ch / 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

/* ===== AnimPreview (redesigned: smaller, checkerboard/crosshair, FPS slider, frame counter) ===== */
function AnimPreview({ frames, canvasFrames, activeFrame, onFrameClick, playing, onTogglePlay, fps, onFpsChange, showCheckerboard, showCrosshair }: {
  frames: FrameInfo[]; canvasFrames: Record<number, HTMLCanvasElement>;
  activeFrame: number; onFrameClick: (idx: number) => void;
  playing: boolean; onTogglePlay: () => void;
  fps: number; onFpsChange: (v: number) => void;
  showCheckerboard: boolean; showCrosshair: boolean;
}) {
  const { t } = useTranslation();
  const cv = useRef<HTMLCanvasElement>(null);
  const timer = useRef<number | null>(null);
  const idxRef = useRef(activeFrame);
  const selected = useMemo(() => frames.filter(f => f.selected).map(f => f.index).sort((a, b) => a - b), [frames]);
  const ZOOM = 2;
  const selIndex = selected.indexOf(activeFrame);
  const displayIdx = selIndex >= 0 ? selIndex + 1 : 0;
  const totalSelected = selected.length;

  useEffect(() => { idxRef.current = activeFrame; }, [activeFrame]);

  useEffect(() => {
    if (!playing || selected.length === 0 || !cv.current) return;
    const delay = Math.round(1000 / Math.max(1, fps));
    const render = () => {
      const can = cv.current; if (!can) return;
      const ctx = can.getContext("2d"); if (!ctx) return;
      const curSelIdx = selected.indexOf(idxRef.current);
      const nextSelIdx = (curSelIdx + 1) % selected.length;
      const fi = selected[nextSelIdx];
      const src = canvasFrames[fi];
      if (src) {
        can.width = src.width * ZOOM;
        can.height = src.height * ZOOM;
        drawFrame(ctx, can.width, can.height, src, showCheckerboard, showCrosshair, false);
      }
      idxRef.current = fi;
      onFrameClick(fi);
    };
    timer.current = window.setInterval(render, delay);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing, fps, selected, canvasFrames, showCheckerboard, showCrosshair, onFrameClick]);

  useEffect(() => {
    if (playing) return;
    if (!cv.current) return;
    const can = cv.current;
    const fi = selected.includes(activeFrame) ? activeFrame : (selected.length > 0 ? selected[0] : -1);
    const src = fi >= 0 ? canvasFrames[fi] : null;
    if (src) {
      can.width = src.width * ZOOM;
      can.height = src.height * ZOOM;
      drawFrame(can.getContext("2d")!, can.width, can.height, src, showCheckerboard, showCrosshair, false);
    }
  }, [activeFrame, playing, selected, canvasFrames, showCheckerboard, showCrosshair]);

  return (
    <div>
      <div className="bg-[#1a1a2e] rounded-s overflow-hidden flex items-center justify-center min-h-[100px]">
        <canvas ref={cv} className="max-w-[200px] max-h-[200px]" />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button onClick={onTogglePlay} className="w-7 h-7 grid place-items-center rounded-s text-txt-1 hover:text-txt-0 hover:bg-bg-3">
          {playing
            ? <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
            : <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>}
        </button>
        <span className="text-[10px] text-txt-3 font-mono ml-auto">
          {selected.length > 0 ? `${t("videoFrames.new.frameCounter", { cur: displayIdx, total: totalSelected })}` : "0/0"}
        </span>
      </div>
      <div className="mt-1.5">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[9px] text-txt-3">{t("videoFrames.new.previewFps")}</span>
          <span className="text-[9px] text-txt-3 font-mono">{fps} FPS</span>
        </div>
        <input type="range" min={1} max={30} step={1} value={fps}
          onChange={e => onFpsChange(Number(e.target.value))}
          className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
      </div>
    </div>
  );
}

/* ===== FrameThumb ===== */
function FrameThumb({ fi, groupColor, onClick, onToggle }: {
  fi: FrameInfo; groupColor?: string; onClick: () => void; onToggle: () => void;
}) {
  return (
    <div className="relative group cursor-pointer" onClick={onClick}>
      <div className="rounded-s overflow-hidden border-2 transition-colors"
        style={{ borderColor: fi.selected ? (groupColor ?? "var(--acc)") : "transparent", width: 72, height: 72 }}>
        <img src={fi.url} alt={fi.name}
          className="w-full h-full object-contain"
          style={{ imageRendering: "pixelated", background: "repeating-conic-gradient(#2a2a3a 0% 25%, #1e1e2e 0% 50%) 0 0 / 16px 16px" }} />
      </div>
      {groupColor && <div className="absolute top-0.5 right-0.5 w-3 h-3 rounded-full border border-line/60" style={{ backgroundColor: groupColor }} />}
      <div className={`absolute top-0.5 left-0.5 w-4 h-4 rounded flex items-center justify-center text-[10px] transition-opacity ${fi.selected ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
        onClick={e => { e.stopPropagation(); onToggle(); }}>
        <div className={`w-3.5 h-3.5 rounded border ${fi.selected ? "bg-[var(--acc)] border-[var(--acc)]" : "bg-bg-2/80 border-line"}`}>
          {fi.selected && <svg viewBox="0 0 24 24" fill="white" width="14" height="14"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" /></svg>}
        </div>
      </div>
      <div className="absolute bottom-0.5 left-0.5 text-[9px] font-mono text-txt-3 bg-bg-0/70 px-1 rounded">
        {fi.index + 1}
      </div>
    </div>
  );
}

/* ===== DownloadMenu ===== */
function DownloadMenu({ busy, onZip, onGif, onPng }: {
  busy: string | null; onZip: () => void; onGif: () => void; onPng: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => { if (!wrapRef.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);
  const isBusy = busy === "zip" || busy === "gif" || busy === "png";
  return (
    <div ref={wrapRef} className="relative">
      <Button variant="outline" loading={isBusy} onClick={() => setOpen(o => !o)}>
        {"\u2B07"} {t("videoFrames.new.download")} {"\u25BE"}
      </Button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-48 rounded-s border border-line bg-bg-2 shadow-2xl z-30 overflow-hidden">
          <DLMenuItem onClick={() => { setOpen(false); onPng(); }} icon={"\uD83D\uDDBC"} title={t("videoFrames.new.dlPng")} hint={t("videoFrames.new.dlPngHint")} />
          <DLMenuItem onClick={() => { setOpen(false); onZip(); }} icon={"\uD83D\uDCE6"} title={t("videoFrames.new.dlZip")} hint={t("videoFrames.new.dlZipHint")} />
          <DLMenuItem onClick={() => { setOpen(false); onGif(); }} icon={"\uD83C\uDF9E"} title={t("videoFrames.new.dlGif")} hint={t("videoFrames.new.dlGifHint")} />
        </div>
      )}
    </div>
  );
}

function DLMenuItem({ icon, title, hint, onClick }: { icon: string; title: string; hint: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full text-left px-3 py-2 hover:bg-[var(--acc)]/10 border-b border-line last:border-b-0">
      <div className="flex items-center gap-2 text-[12px] text-txt-1"><span>{icon}</span><span>{title}</span></div>
      <div className="text-[10.5px] text-txt-3 mt-0.5 ml-6">{hint}</div>
    </button>
  );
}

/* ================================================================
   ExtractTab — 视频序列帧提取主组件 (3-step flow)
   ================================================================ */
export function ExtractTab({ onNewJob }: { onNewJob?: () => void }) {
  const { t } = useTranslation();
  const fileRef = useRef<HTMLInputElement>(null);

  // === Step ===
  const [step, setStep] = useState<Step>(1);

  // === Source ===
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [probe, setProbe] = useState<VFProbeResponse | null>(null);
  const [uploading, setUploading] = useState(false);

  // === Extract Params ===
  const [fps, setFps] = useState(8);
  const [maxFrames, setMaxFrames] = useState(300);
  const [startSec, setStartSec] = useState(0);
  const [endSec, setEndSec] = useState(0);

  // === Pre-extract Crop (percentage 0–50 of each side) ===
  const [cropHPct, setCropHPct] = useState(0);
  const [cropVPct, setCropVPct] = useState(0);
  const [syncCrop, setSyncCrop] = useState(true);

  // === Job ===
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string>("");
  const [jobResult, setJobResult] = useState<VFJobResponse["result"] | null>(null);
  const [submitErr, setSubmitErr] = useState<string | null>(null);

  // === Frames ===
  const [frames, setFrames] = useState<FrameInfo[]>([]);
  const [canvasFrames, setCanvasFrames] = useState<Record<number, HTMLCanvasElement>>({});
  // === Key Frame Selection ===
  const [keyFrameCount, setKeyFrameCount] = useState(8);
  const [keyFrameMode, setKeyFrameMode] = useState<"uniform" | "diversity" | "cycle">("cycle");
  const [selecting, setSelecting] = useState(false);
  const [cycleInfo, setCycleInfo] = useState<string | null>(null);

  // === AI Matte Progress ===
  const [matteProgress, setMatteProgress] = useState<{ cur: number; total: number } | null>(null);

  // === Step 2: Animation Preview states ===
  const [activeFrame, setActiveFrame] = useState(0);
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const [previewFps, setPreviewFps] = useState(8);
  const [showCheckerboard, setShowCheckerboard] = useState(false);
  const [showCrosshair, setShowCrosshair] = useState(false);

  // === Step 2: Batch operations ===
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);
  const [gridCols, setGridCols] = useState(8);

  // === Export ===
  const [cellSize, setCellSize] = useState(0);
  const [customCell, setCustomCell] = useState(64);
  const [layoutCols, setLayoutCols] = useState(8);
  const [layoutRows, setLayoutRows] = useState(4);
  const [margin, setMargin] = useState(0);
  const [spacing, setSpacing] = useState(0);
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("pixel");
  const [busy, setBusy] = useState<string | null>(null);
  const [exportPreviewUrl, setExportPreviewUrl] = useState<string | null>(null);
  const smooth = processingMode === "smooth";

  // === Selected frames (from canvasFrames) for export ===
  const selectedExportFrames = useMemo(() => {
    return frames
      .filter(f => f.selected)
      .map(f => canvasFrames[f.index])
      .filter((c): c is HTMLCanvasElement => !!c);
  }, [frames, canvasFrames]);

  const maxCells = layoutCols * layoutRows;
  const exportFrameCount = Math.min(selectedExportFrames.length, maxCells);

  // === Real-time export preview ===
  useEffect(() => {
    if (selectedExportFrames.length === 0) { setExportPreviewUrl(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const raw: Frame[] = selectedExportFrames.slice(0, maxCells).map(c => ({ canvas: c, width: c.width, height: c.height }));
        const blob = await recombineFrames(raw, layoutCols, {
          cellW: cellSize || undefined, cellH: cellSize || undefined,
          align: "bottom", smooth,
        });
        if (!cancelled) {
          if (exportPreviewUrl) URL.revokeObjectURL(exportPreviewUrl);
          setExportPreviewUrl(URL.createObjectURL(blob));
        }
      } catch { if (!cancelled) setExportPreviewUrl(null); }
    })();
    return () => { cancelled = true; };
  }, [selectedExportFrames, layoutCols, layoutRows, cellSize, smooth, maxCells]);

  const canStep2 = jobStatus === "completed" && !!jobResult;
  const canStep3 = frames.length > 0;
  const selectedCount = useMemo(() => frames.filter(f => f.selected).length, [frames]);

  // === Crop data (percentage → pixels) ===
  const cropLeft = probe ? Math.round(probe.width * cropHPct / 100) : 0;
  const cropRight = probe ? Math.round(probe.width * cropHPct / 100) : 0;
  const cropTop = probe ? Math.round(probe.height * cropVPct / 100) : 0;
  const cropBottom = probe ? Math.round(probe.height * cropVPct / 100) : 0;

  const cropW = probe ? Math.max(1, probe.width - cropLeft - cropRight) : 0;
  const cropH2 = probe ? Math.max(1, probe.height - cropTop - cropBottom) : 0;

  // === Handlers ===
  const handleFile = useCallback(async (f: File) => {
    setFile(f); setVideoUrl(URL.createObjectURL(f)); setUploading(true); setSubmitErr(null);
    try {
      const p = await api.probeVideo(f); setProbe(p);
      setEndSec(p.duration);
      setCropHPct(0); setCropVPct(0);
      setFps(Math.min(8, Math.round(p.original_fps)));
    } catch (e) { setSubmitErr(String(e)); setProbe(null); }
    finally { setUploading(false); }
  }, []);

  const onLocalFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    handleFile(f); e.target.value = "";
  };

  const onCropH = (v: number) => { setCropHPct(v); if (syncCrop) setCropVPct(v); };
  const onCropV = (v: number) => { setCropVPct(v); if (syncCrop) setCropHPct(v); };

  // === Submit Extract ===
  const handleSubmit = async () => {
    if (!file || !probe) return;
    setSubmitErr(null); setJobStatus("processing");
    try {
      const res = await api.createVFJob(file, {
        fps, max_frames: maxFrames, start_sec: startSec, end_sec: endSec, spacing: 4,
        layout_mode: "auto_square", columns: 8,
        crop_left: cropLeft, crop_right: cropRight,
        crop_top: cropTop, crop_bottom: cropBottom,
      });
      setJobId(res.job_id);
      pollJob(res.job_id);
    } catch (e) { setSubmitErr(String(e)); setJobStatus(""); }
  };

  const pollJob = async (id: string) => {
    const poll = async () => {
      try {
        const j = await api.getVFJob(id);
        setJobStatus(j.status);
        if (j.status === "completed") { setJobResult(j.result); await loadFrames(id); }
        else if (j.status === "failed") { setSubmitErr(j.error?.message || "Unknown error"); return; }
        else { setTimeout(() => poll(), 1500); }
      } catch (e) { setSubmitErr(String(e)); }
    };
    poll();
  };

  const loadFrames = async (id: string) => {
    try {
      const flist = await api.getVFFrames(id);
      const fi: FrameInfo[] = flist.frames.map((f, i) => ({
        name: f.name, url: f.url, index: i, selected: true
      }));
      setFrames(fi);
      const cvs: Record<number, HTMLCanvasElement> = {};
      await Promise.all(fi.map(async (f) => {
        try {
          const img = await loadImage(f.url);
          const c = document.createElement("canvas");
          c.width = img.naturalWidth; c.height = img.naturalHeight;
          c.getContext("2d")!.drawImage(img, 0, 0);
          cvs[f.index] = c;
        } catch {}
      }));
      setCanvasFrames(cvs);
      setLayoutCols(Math.min(fi.length, 8));
      setLayoutRows(Math.min(Math.ceil(fi.length / 8), 4));
      setActiveFrame(0);
      setStep(2);
      onNewJob?.();
    } catch (e) { setSubmitErr(String(e)); }
  };

  // === Frame Selection ===
  const toggleSelect = (idx: number) => {
    setFrames(prev => prev.map((f, i) => {
      if (i === idx) return { ...f, selected: !f.selected };
      return f;
    }));
  };
  const handleFrameClick = (idx: number) => {
    setActiveFrame(idx);
    setFrames(prev => prev.map((f, i) => ({ ...f, selected: i === idx ? true : f.selected })));
  };
  const selectAll = (v: boolean) => setFrames(prev => prev.map(f => ({ ...f, selected: v })));
  const deleteFrames = () => {
    setFrames(prev => {
      const kept = prev.filter(f => !f.selected);
      return kept.map((f, i) => ({ ...f, index: i }));
    });
    setActiveFrame(0);
    setPreviewPlaying(false);
  };

  // === Batch Operations ===
  const handleFlipH = () => {
    setCanvasFrames(prev => {
      const next = { ...prev };
      for (const f of frames) {
        if (f.selected && next[f.index]) {
          const flipped = flipFrameH({ canvas: next[f.index], width: next[f.index].width, height: next[f.index].height });
          next[f.index] = flipped.canvas;
        }
      }
      return next;
    });
  };

  const applyOffset = () => {
    if (offsetX === 0 && offsetY === 0) return;
    setCanvasFrames(prev => {
      const next = { ...prev };
      for (const f of frames) {
        if (f.selected && next[f.index]) {
          const shifted = shiftFrame({ canvas: next[f.index], width: next[f.index].width, height: next[f.index].height }, offsetX, offsetY);
          next[f.index] = shifted.canvas;
        }
      }
      return next;
    });
    setOffsetX(0); setOffsetY(0);
  };

  const handleAiMatte = async () => {
    const selected = frames.filter(f => f.selected);
    if (selected.length === 0) return;
    setBusy("matte");
    setMatteProgress({ cur: 0, total: selected.length });
    try {
      const nextCanvasFrames = { ...canvasFrames };
      const urlUpdates: Record<number, string> = {};
      let done = 0;
      for (const f of selected) {
        try {
          const blob = await urlToBlob(f.url);
          const file = new File([blob], f.name, { type: "image/png" });
          const resultBlob = await api.matteImage(file);
          const c = document.createElement("canvas");
          const img = await loadImage(URL.createObjectURL(resultBlob));
          c.width = img.naturalWidth;
          c.height = img.naturalHeight;
          c.getContext("2d")!.drawImage(img, 0, 0);
          nextCanvasFrames[f.index] = c;
          // also create blob URL for frame thumbnail
          const thumbBlob = await new Promise<Blob | null>(resolve => c.toBlob(resolve, "image/png"));
          if (thumbBlob) urlUpdates[f.index] = URL.createObjectURL(thumbBlob);
        } catch {
          // skip individual frame failures
        }
        done++;
        setMatteProgress({ cur: done, total: selected.length });
      }
      setCanvasFrames(nextCanvasFrames);
      // update frame URLs so thumbnails show matted result
      if (Object.keys(urlUpdates).length > 0) {
        setFrames(prev => prev.map(f => {
          const newUrl = urlUpdates[f.index];
          return newUrl ? { ...f, url: newUrl } : f;
        }));
      }
    } catch (e) {
      setSubmitErr(String(e));
    } finally {
      setBusy(null);
      setMatteProgress(null);
    }
  };

  // === Key Frame Selection ===
  const applyFrameSelection = (indices: number[]) => {
    const idxSet = new Set(indices);
    setFrames(prev => prev.map((f, i) => ({ ...f, selected: idxSet.has(i) })));
  };

  const handleUniformSelect = () => {
    const total = frames.length;
    const target = keyFrameCount;
    if (total <= target) { applyFrameSelection(Array.from({ length: total }, (_, i) => i)); return; }
    const indices: number[] = [];
    for (let i = 0; i < target; i++) indices.push(Math.round(i * (total - 1) / (target - 1)));
    applyFrameSelection(indices);
    setCycleInfo(null);
  };

  const handleDiversitySelect = async () => {
    setSelecting(true); setCycleInfo(null);
    try { applyFrameSelection(await diversitySelectFrames(frames.map(f => f.url), keyFrameCount)); }
    catch { handleUniformSelect(); }
    finally { setSelecting(false); }
  };

  const handleCycleSelect = async () => {
    setSelecting(true); setCycleInfo(null);
    try {
      const { indices, cycleLen } = await cycleDetectAndSample(frames.map(f => f.url), keyFrameCount);
      applyFrameSelection(indices);
      setCycleInfo(cycleLen ? `检测到循环周期: ${cycleLen} 帧` : "未检测到明显循环，使用均匀采样");
    } catch {
      handleUniformSelect();
      setCycleInfo("分析失败，使用均匀采样");
    }
    finally { setSelecting(false); }
  };

  const handleKeyFrameSelect = () => {
    if (keyFrameMode === "uniform") handleUniformSelect();
    else if (keyFrameMode === "diversity") handleDiversitySelect();
    else handleCycleSelect();
  };

  // === Save Frames ===
  const handleSaveFrames = async () => {
    if (!jobId) return;
    setBusy("save");
    try {
      const bases: string[] = [];
      for (const f of frames) {
        const blob = await urlToBlob(f.url);
        bases.push(await blobToBase64(blob));
      }
      await api.saveVFrames(jobId, { frames: bases });
      await loadFrames(jobId);
    } catch (e) { setSubmitErr(String(e)); }
    finally { setBusy(null); }
  };

  // === Compose ===
  const doCompose = async () => {
    if (!jobId) return;
    setBusy("compose");
    try {
      const res = await api.composeVFSprite(jobId, {
        columns: layoutCols, margin, spacing, cell_size: cellSize, smooth,
      });
      setJobResult(res);
    } catch (e) { setSubmitErr(String(e)); }
    finally { setBusy(null); }
  };

  // === Export ===
  const buildExportRaw = (): Frame[] =>
    selectedExportFrames.slice(0, maxCells).map(c => ({ canvas: c, width: c.width, height: c.height }));

  const handlePng = async () => {
    setBusy("png");
    try {
      const blob = await recombineFrames(buildExportRaw(), layoutCols, {
        cellW: cellSize || undefined, cellH: cellSize || undefined, align: "bottom", smooth,
      });
      downloadBlob(blob, "video-frames.png");
    } catch (e) { setSubmitErr(String(e)); }
    finally { setBusy(null); }
  };

  const handleZip = async () => {
    setBusy("zip");
    try {
      const blob = await exportFramesZip(buildExportRaw(), "frame", {
        cellW: cellSize || undefined, cellH: cellSize || undefined, align: "bottom", smooth,
      });
      downloadBlob(blob, "video-frames.zip");
    } catch (e) { setSubmitErr(String(e)); }
    finally { setBusy(null); }
  };

  const handleGif = async () => {
    setBusy("gif");
    try {
      const blob = await exportFramesGif(buildExportRaw(), 100, "bottom", {
        cellW: cellSize || undefined, cellH: cellSize || undefined, smooth,
      });
      downloadBlob(blob, "video-frames.gif");
    } catch (e) { setSubmitErr(String(e)); }
    finally { setBusy(null); }
  };

  const handleSaveLibrary = async () => {
    setBusy("savelib");
    try {
      const blob = await recombineFrames(buildExportRaw(), layoutCols, {
        cellW: cellSize || undefined, cellH: cellSize || undefined, align: "bottom", smooth,
      });
      const file2 = new File([blob], "video-frames-sheet.png", { type: "image/png" });
      await api.uploadAsset(file2, "video-frames");
    } catch (e) { setSubmitErr(String(e)); }
    finally { setBusy(null); }
  };

  const groupColorMap = {} as Record<number, string>;

  // ==================== RENDER ====================
  return (
    <div className="space-y-4">
      <VFStepper step={step} onJump={setStep} canStep2={canStep2} canStep3={canStep3} />

      {/* ======== STEP 1: Source & Params ======== */}
      {step === 1 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card title={t("videoFrames.new.sourceTitle")} subtitle={t("videoFrames.new.sourceHint")}>
            {!videoUrl ? (
              <div className="border-2 border-dashed border-line rounded-s p-8 text-center cursor-pointer hover:border-[var(--acc)] hover:bg-[var(--acc)]/5 transition-colors"
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); e.stopPropagation(); }}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) handleFile(f); }}>
                <div className="text-3xl mb-2">🎬</div>
                <div className="text-[13px] text-txt-1 font-medium">{t("videoFrames.new.dropTitle")}</div>
                <div className="text-[10.5px] text-txt-3 mt-1">{t("videoFrames.new.dropHint")}</div>
              </div>
            ) : (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-[12px] text-txt-1 font-medium truncate flex-1">{file?.name}</span>
                  <Button size="sm" variant="ghost" onClick={() => { setVideoUrl(null); setFile(null); setProbe(null); setJobId(null); setJobStatus(""); setJobResult(null); setFrames([]); }}>
                    {t("videoFrames.new.changeFile")}
                  </Button>
                </div>
                {uploading && <div className="text-[11px] text-txt-3 py-4 text-center">{t("videoFrames.extract.uploading")}</div>}
                {probe && !uploading && (
                  <>
                    <div className="rounded-l border border-line bg-bg-2 p-3 mb-3">
                      <div className="flex items-center gap-3">
                        <div className="flex-1">
                          <Field label={t("videoFrames.new.fps")}>
                            <TextInput type="number" value={fps} onChange={e => setFps(Math.max(1, Number(e.target.value)))} min={1} max={60} />
                          </Field>
                        </div>
                        <div className="flex-1">
                          <Field label={t("videoFrames.new.maxFrames")}>
                            <TextInput type="number" value={maxFrames} onChange={e => setMaxFrames(Math.max(1, Number(e.target.value)))} min={1} max={9999} />
                          </Field>
                        </div>
                      </div>
                      <div className="text-[10px] text-txt-3 mt-1">
                        {t("videoFrames.new.estimatedFrames")}: {Math.min(maxFrames, Math.floor((endSec - startSec) * fps))}
                      </div>
                    </div>

                    {/* Pre-extract Crop */}
                    <div className="rounded-l border border-line bg-bg-2 p-3 mt-3">
                      <div className="text-[11px] font-medium text-txt-1 mb-2">{t("videoFrames.new.cropTitle")}</div>
                      <div className="flex items-center gap-2 mb-2">
                        <button onClick={() => setSyncCrop(!syncCrop)}
                          className={`px-2 py-0.5 text-[10px] rounded-s border transition-colors ${syncCrop ? "border-[var(--acc)] bg-[var(--acc)]/10 text-[var(--acc)]" : "border-line bg-bg-3 text-txt-2"}`}>
                          {syncCrop ? "🔗 synced" : "🔓 separate"}
                        </button>
                        <span className="text-[9px] text-txt-3">{t("videoFrames.new.cropHint")}</span>
                      </div>

                      {/* Video info reference */}
                      <div className="text-[9px] text-txt-3 mb-2">
                        🎬 {probe.width} × {probe.height}
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] text-txt-2">{t("videoFrames.new.cropHorizontal")}</span>
                            <span className="text-[10px] text-txt-3 font-mono">{cropHPct}% → {cropLeft}px</span>
                          </div>
                          <input type="range" min={0} max={50} step={0.5} value={cropHPct}
                            onChange={e => onCropH(Number(e.target.value))}
                            className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
                        </div>
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] text-txt-2">{t("videoFrames.new.cropVertical")}</span>
                            <span className="text-[10px] text-txt-3 font-mono">{cropVPct}% → {cropTop}px</span>
                          </div>
                          <input type="range" min={0} max={50} step={0.5} value={cropVPct}
                            onChange={e => onCropV(Number(e.target.value))}
                            className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
                        </div>
                      </div>
                      {(cropHPct > 0 || cropVPct > 0) && (
                        <div className="mt-2 text-[10px] text-txt-3 space-y-0.5">
                          <div>每侧裁切: {cropHPct > 0 ? <span className="text-txt-1">↔{cropLeft}px</span> : "—"} {cropVPct > 0 ? <span className="text-txt-1">↕{cropTop}px</span> : "—"}</div>
                          <div className="font-medium text-txt-0">
                            {t("videoFrames.new.cropResult")}: <span className="text-[var(--acc)]">{cropW} × {cropH2}</span>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="mt-3">
                      <Button variant="primary" className="!w-full" loading={jobStatus === "processing"} onClick={handleSubmit}>
                        {jobStatus === "processing" ? t("videoFrames.extract.processing") : t("videoFrames.new.submit")}
                      </Button>
                    </div>
                    {submitErr && <div className="mt-2 text-[11px] text-red-400">{submitErr}</div>}
                    {jobStatus === "processing" && <div className="mt-2 text-[11px] text-txt-3">🔄 Processing...</div>}
                  </>
                )}
              </div>
            )}
            <input ref={fileRef} type="file" accept="video/*" className="hidden" onChange={onLocalFile} />
          </Card>

          {/* Right: Video Preview */}
          {videoUrl && probe && (
            <Card title={t("videoFrames.new.videoPreview")}>
              <VideoPlayer videoUrl={videoUrl} probe={probe} startSec={startSec} endSec={endSec}
                onStartChange={setStartSec} onEndChange={setEndSec}
                cropHPct={cropHPct} cropVPct={cropVPct} />
            </Card>
          )}
        </div>
      )}

      {/* ======== STEP 2: Frame Animation Processing (redesigned) ======== */}
      {step === 2 && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* Left: Frame Grid (3 cols) */}
          <div className="lg:col-span-3">
            <Card
              title={`${t("videoFrames.new.framesTitle")} (${selectedCount}/${frames.length})`}
              actions={
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="ghost" onClick={() => selectAll(true)}>{t("videoFrames.new.selectAll")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => selectAll(false)}>{t("videoFrames.new.selectNone")}</Button>
                  <select className="h-7 rounded-s border border-line bg-bg-2 text-[10px] px-1"
                    value={gridCols} onChange={e => setGridCols(Number(e.target.value))}>
                    {[2,3,4,6,8].map(c => <option key={c} value={c}>{c} cols</option>)}
                  </select>
                </div>
              }>
              <div className="flex flex-wrap gap-2 max-h-[55vh] overflow-y-auto p-1" style={{ maxWidth: gridCols * 82 }}>
                {frames.map((f, i) => (
                  <FrameThumb key={i} fi={f} groupColor={groupColorMap[i]}
                    onClick={() => { handleFrameClick(i); setPreviewPlaying(false); }}
                    onToggle={() => toggleSelect(i)} />
                ))}
              </div>
            </Card>

            {/* Key Frame Selection */}
            <Card title="关键帧选择" subtitle="从序列帧中自动选出适合循环动画的帧">
              <div className="space-y-2.5">
                {/* Mode toggle — 3 options */}
                <div className="flex rounded-s border border-line overflow-hidden">
                  {(["uniform", "cycle", "diversity"] as const).map(mode => (
                    <button key={mode} onClick={() => { setKeyFrameMode(mode); setCycleInfo(null); }}
                      className={`flex-1 px-2 py-1 text-[10px] transition-colors ${keyFrameMode === mode ? "bg-[var(--acc)] text-white" : "bg-bg-3 text-txt-2 hover:text-txt-1"}`}>
                      {{ uniform: "均匀", cycle: "循环检测", diversity: "差异最大" }[mode]}
                    </button>
                  ))}
                </div>
                {/* Mode hint */}
                <div className="text-[9px] text-txt-3">
                  {{ uniform: "时间轴等距选帧，适合动作匀速的动画",
                     cycle: "自动检测运动循环周期，在一个完整循环内均匀选帧",
                     diversity: "选出画面差异最大的帧，覆盖完整动作范围" }[keyFrameMode]}
                </div>
                {/* Target count + info */}
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-txt-2 shrink-0">目标帧数</span>
                  <input type="number" value={keyFrameCount} min={2} max={Math.max(2, frames.length)}
                    onChange={e => setKeyFrameCount(Math.max(2, Math.min(frames.length, Number(e.target.value) || 2)))}
                    className="w-16 h-7 rounded-s border border-line bg-bg-2 text-[11px] text-center font-mono" />
                  <span className="text-[9px] text-txt-3">/ {frames.length} 帧</span>
                  {cycleInfo && <span className="text-[9px] text-[var(--acc)] ml-auto">{cycleInfo}</span>}
                </div>
                {/* Single action button */}
                <Button size="sm" variant="primary" loading={selecting} onClick={handleKeyFrameSelect} className="!w-full !text-[10px]">
                  {{ uniform: "⏱ 均匀选", cycle: "🔄 循环检测选", diversity: "🎯 差异选" }[keyFrameMode]} {keyFrameCount} 帧
                </Button>
              </div>
            </Card>
          </div>

          {/* Right: Operations Sidebar (2 cols) */}
          <div className="lg:col-span-2 space-y-3">
            {/* Animation Preview + Toggles */}
            <Card title={t("videoFrames.new.animPreview")}>
              <AnimPreview frames={frames} canvasFrames={canvasFrames}
                activeFrame={activeFrame} onFrameClick={setActiveFrame}
                playing={previewPlaying} onTogglePlay={() => setPreviewPlaying(p => !p)}
                fps={previewFps} onFpsChange={setPreviewFps}
                showCheckerboard={showCheckerboard} showCrosshair={showCrosshair} />
              <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-line/40">
                <button onClick={() => setShowCheckerboard(c => !c)}
                  className={`flex items-center gap-1 px-2 py-0.5 rounded-s text-[10px] border transition-colors ${showCheckerboard ? "border-[var(--acc)] bg-[var(--acc)]/10 text-[var(--acc)]" : "border-line bg-bg-3 text-txt-2 hover:text-txt-1"}`}>
                  ▦ {t("videoFrames.new.checkerboard")}
                </button>
                <button onClick={() => setShowCrosshair(c => !c)}
                  className={`flex items-center gap-1 px-2 py-0.5 rounded-s text-[10px] border transition-colors ${showCrosshair ? "border-[var(--acc)] bg-[var(--acc)]/10 text-[var(--acc)]" : "border-line bg-bg-3 text-txt-2 hover:text-txt-1"}`}>
                  ＋ {t("videoFrames.new.crosshair")}
                </button>
              </div>
            </Card>

            {/* Batch Operations */}
            <Card title={t("videoFrames.new.batchOps")}>
              <div className="space-y-2">
                <div className="grid grid-cols-3 gap-1">
                  <Button size="sm" variant="outline" onClick={handleAiMatte} disabled={busy === "matte"} loading={busy === "matte"}>
                    ✨ {t("videoFrames.new.aiMatte")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleFlipH}>
                    ↔ {t("videoFrames.new.flipH")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={deleteFrames} disabled={selectedCount === 0}>
                    🗑 {t("videoFrames.new.deleteSel", { n: selectedCount })}
                  </Button>
                </div>
                {matteProgress && (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[9px]">
                      <span className="text-txt-2">AI抠图进度</span>
                      <span className="text-txt-3 font-mono">{matteProgress.cur}/{matteProgress.total} ({Math.round(matteProgress.cur / matteProgress.total * 100)}%)</span>
                    </div>
                    <div className="w-full h-1.5 rounded-full bg-bg-3 overflow-hidden">
                      <div className="h-full rounded-full bg-[var(--acc)] transition-all duration-300"
                        style={{ width: `${(matteProgress.cur / matteProgress.total) * 100}%` }} />
                    </div>
                  </div>
                )}

                {/* Pixel Offset — single row */}
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-txt-3 shrink-0">{t("videoFrames.new.offset1px")}</span>
                  <div className="flex items-center gap-0.5">
                    <button onClick={() => setOffsetX(x => x - 1)} className="w-6 h-6 grid place-items-center rounded border border-line bg-bg-2 text-[11px] text-txt-1 hover:bg-bg-3" title="←">←</button>
                    <button onClick={() => setOffsetY(y => y + 1)} className="w-6 h-6 grid place-items-center rounded border border-line bg-bg-2 text-[11px] text-txt-1 hover:bg-bg-3" title="↑">↑</button>
                    <button onClick={() => setOffsetY(y => y - 1)} className="w-6 h-6 grid place-items-center rounded border border-line bg-bg-2 text-[11px] text-txt-1 hover:bg-bg-3" title="↓">↓</button>
                    <button onClick={() => setOffsetX(x => x + 1)} className="w-6 h-6 grid place-items-center rounded border border-line bg-bg-2 text-[11px] text-txt-1 hover:bg-bg-3" title="→">→</button>
                    <span className="text-[9px] text-txt-3 font-mono px-1">{offsetX},{offsetY}</span>
                  </div>
                  <Button size="sm" variant="primary" onClick={applyOffset} disabled={offsetX === 0 && offsetY === 0} className="!px-2 !py-0.5 !text-[9px] shrink-0">
                    {t("videoFrames.new.offsetApply")}
                  </Button>
                </div>
              </div>
            </Card>

            {/* Navigation */}
            <div className="flex items-center justify-between pt-1">
              <Button variant="ghost" size="sm" onClick={() => { setStep(1); setPreviewPlaying(false); }}>
                ← {t("videoFrames.new.backAdjust")}
              </Button>
              <Button variant="primary" size="sm" onClick={() => setStep(3)} disabled={!canStep3}>
                {t("videoFrames.new.toExport")} →
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ======== STEP 3: Export ======== */}
      {step === 3 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left: Export Controls */}
          <Card title={t("videoFrames.new.exportTitle")} subtitle={`${exportFrameCount}/${selectedExportFrames.length} 帧`}>
            <div className="space-y-3">
              {/* Cell Size */}
              <div>
                <div className="text-[10px] text-txt-2 mb-1.5">单帧尺寸</div>
                <div className="flex flex-wrap gap-1">
                  {CELL_PRESETS.map(sz => (
                    <button key={sz} onClick={() => setCellSize(sz)}
                      className={`px-1.5 py-0.5 text-[10px] rounded-s border transition-colors ${cellSize === sz ? "border-[var(--acc)] bg-[var(--acc)]/10 text-[var(--acc)]" : "border-line bg-bg-3 text-txt-2 hover:text-txt-1"}`}>
                      {sz === 0 ? "原始" : sz}
                    </button>
                  ))}
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <span className="text-[9px] text-txt-3">自定义:</span>
                  <input type="number" value={customCell} min={1} max={4096}
                    onChange={e => { const v = Number(e.target.value); setCustomCell(v); setCellSize(v); }}
                    className="w-16 h-6 rounded-s border border-line bg-bg-2 text-[10px] text-center font-mono" />
                </div>
              </div>

              {/* Layout sliders */}
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <div>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px] text-txt-2">列数</span>
                    <span className="text-[9px] text-txt-3 font-mono">{layoutCols}</span>
                  </div>
                  <input type="range" min={1} max={16} value={layoutCols}
                    onChange={e => setLayoutCols(Number(e.target.value))}
                    className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px] text-txt-2">行数</span>
                    <span className="text-[9px] text-txt-3 font-mono">{layoutRows}</span>
                  </div>
                  <input type="range" min={1} max={16} value={layoutRows}
                    onChange={e => setLayoutRows(Number(e.target.value))}
                    className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px] text-txt-2">边距</span>
                    <span className="text-[9px] text-txt-3 font-mono">{margin}px</span>
                  </div>
                  <input type="range" min={0} max={64} value={margin}
                    onChange={e => setMargin(Number(e.target.value))}
                    className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-[10px] text-txt-2">间距</span>
                    <span className="text-[9px] text-txt-3 font-mono">{spacing}px</span>
                  </div>
                  <input type="range" min={0} max={64} value={spacing}
                    onChange={e => setSpacing(Number(e.target.value))}
                    className="w-full h-1 accent-[var(--acc)] cursor-pointer" />
                </div>
              </div>

              {/* Processing Mode */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-txt-2 shrink-0">处理模式</span>
                <div className="flex rounded-s border border-line overflow-hidden ml-auto">
                  <button onClick={() => setProcessingMode("pixel")}
                    className={`px-2 h-6 text-[10px] transition-colors ${processingMode === "pixel" ? "bg-[var(--acc)] text-white" : "bg-bg-3 text-txt-2 hover:text-txt-1"}`}>
                    {t("videoFrames.new.modePixel")}
                  </button>
                  <button onClick={() => setProcessingMode("smooth")}
                    className={`px-2 h-6 text-[10px] transition-colors ${processingMode === "smooth" ? "bg-[var(--acc)] text-white" : "bg-bg-3 text-txt-2 hover:text-txt-1"}`}>
                    {t("videoFrames.new.modeSmooth")}
                  </button>
                </div>
              </div>

              {selectedExportFrames.length > maxCells && (
                <div className="text-[9px] text-amber-400">
                  ⚠ 选中 {selectedExportFrames.length} 帧，网格 {layoutCols}×{layoutRows}={maxCells} 格，将只导出前 {maxCells} 帧
                </div>
              )}

              {/* Action Buttons */}
              <div className="grid grid-cols-2 gap-2">
                <Button variant="primary" loading={busy === "savelib"} onClick={handleSaveLibrary} title={t("videoFrames.new.saveTooltip")}>
                  💾 {t("videoFrames.new.saveLibrary")}
                </Button>
                <DownloadMenu busy={busy} onZip={handleZip} onGif={handleGif} onPng={handlePng} />
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-line">
                <Button variant="ghost" onClick={() => setStep(2)}>
                  ← {t("videoFrames.new.backAdjust")}
                </Button>
              </div>
            </div>
          </Card>

          {/* Right: Client-side Preview */}
          <Card title={t("videoFrames.new.exportPreview")}>
            {exportPreviewUrl ? (
              <div className="bg-[#1a1a2e] rounded-s overflow-hidden flex items-center justify-center min-h-[200px]">
                <img src={exportPreviewUrl} alt="sprite preview"
                  className="max-w-full" style={{ imageRendering: smooth ? "auto" : "pixelated" }} />
              </div>
            ) : (
              <div className="bg-[#1a1a2e] rounded-s flex items-center justify-center min-h-[200px] text-[11px] text-txt-3">
                选择至少 1 帧后自动预览
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

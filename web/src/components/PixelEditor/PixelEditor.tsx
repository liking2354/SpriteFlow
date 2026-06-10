/**
 * PixelEditor — 精细处理像素编辑器
 *
 * FrameRonin架构: 事件在container, canvas pointerEvents:none,
 * displayScale=fitScale×zoomFactor, SVG data URI光标, 30步历史栈.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

type Tool = "brush" | "eraser" | "superEraser" | "selectMove" | "eyedropper" | "pan";
type BrushShape = "round" | "square";
type ToolDef = { id: Tool; label: string; icon: ReactNode };
type SelRect = { x: number; y: number; w: number; h: number };
type Marquee = { ax: number; ay: number; bx: number; by: number };
type MoveDrag = { scx: number; scy: number; dix: number; diy: number };

/* ---- 统一 SVG 图标 18×18, viewBox 0 0 24 24 ---- */
const S = { w: 18, h: 18 };
const iconAttrs = (d: string) => ({
  ...S, viewBox: "0 0 24 24",
  fill: "none", stroke: "currentColor", strokeWidth: 1.8,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
  children: <path d={d} />,
});

const toolIcons: Record<Tool, ReactNode> = {
  pan:               <svg {...iconAttrs("M12 2v20 M2 12h20 M7 7l5-5 5 5 M17 17l-5 5-5-5")} />,
  brush:             <svg {...iconAttrs("M18.4 2.6a2.1 2.1 0 013 3L12 15l-5 5-3 1 1-3 5-5z M10 12l4 4")} />,
  eraser:            <svg {...iconAttrs("M20 20H7l-5-5a1.4 1.4 0 010-2l10-10a1.4 1.4 0 012 0l5 5a1.4 1.4 0 010 2L14 15 M6 11h9")} />,
  superEraser:       <svg {...iconAttrs("M15 4V2 M15 16v-2 M8 9h2 M20 9h2 M17.5 6.5L19 5 M10.5 14.5L9 16 M3 21l9-9")} />,
  selectMove:        <svg {...iconAttrs("M3 3h7v2H5v5H3V3z M21 21h-7v-2h5v-5h2v7z M21 3h-7v2h5v5h2V3z M3 21v-7h2v5h5v2H3z")} />,
  eyedropper:        <svg {...iconAttrs("M18.9 2.1a3.1 3.1 0 00-4.5 0l-1.3 1.3-1-.3a1.4 1.4 0 00-1.5.4l-1 1 7 7 1-1a1.4 1.4 0 00.4-1.5l-.3-1 1.3-1.3a3.1 3.1 0 000-4.5z M10.6 14.4l-7 7")} />,
};

const TOOLS: ToolDef[] = [
  { id: "pan",         label: "平移",     icon: toolIcons.pan },
  { id: "brush",       label: "画笔",     icon: toolIcons.brush },
  { id: "eraser",      label: "橡皮",     icon: toolIcons.eraser },
  { id: "superEraser", label: "超级橡皮", icon: toolIcons.superEraser },
  { id: "selectMove",  label: "框选移动", icon: toolIcons.selectMove },
  { id: "eyedropper",  label: "吸管",     icon: toolIcons.eyedropper },
];

function pointInSelRect(px: number, py: number, r: SelRect): boolean {
  return px >= r.x && px < r.x + r.w && py >= r.y && py < r.y + r.h;
}

interface Props { src: string; onExport?: (blob: Blob) => void; onReset?: () => void; }

export function PixelEditor({ src, onExport, onReset }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [tool, setTool] = useState<Tool>("pan");
  const toolRef = useRef<Tool>("pan"); toolRef.current = tool;
  const [brushColor, setBrushColor] = useState("#ff0000");
  const [brushSize, setBrushSize] = useState(4);
  const brushSizeRef = useRef(4); brushSizeRef.current = brushSize;
  const [brushShape, setBrushShape] = useState<BrushShape>("round");
  const brushShapeRef = useRef<BrushShape>("round"); brushShapeRef.current = brushShape;
  const [eraserSize, setEraserSize] = useState(8);
  const eraserSizeRef = useRef(8); eraserSizeRef.current = eraserSize;
  const [superTolerance, setSuperTolerance] = useState(30);
  const superToleranceRef = useRef(30); superToleranceRef.current = superTolerance;

  const [contrast, setContrast] = useState(1.0);
  const contrastRef = useRef(1.0); contrastRef.current = contrast;
  const contrastBaselineRef = useRef<ImageData | null>(null);

  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const imgSizeRef = useRef<{ w: number; h: number } | null>(null); imgSizeRef.current = imgSize;
  const [loading, setLoading] = useState(true);

  const [fitScale, setFitScale] = useState(1);
  const fitScaleRef = useRef(1); fitScaleRef.current = fitScale;
  const [zoomFactor, setZoomFactor] = useState(1);
  const zoomFactorRef = useRef(1); zoomFactorRef.current = zoomFactor;
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const offsetRef = useRef({ x: 0, y: 0 }); offsetRef.current = offset;
  const displayScale = fitScale * zoomFactor;

  const [drawing, setDrawing] = useState(false);
  const drawingRef = useRef(false); drawingRef.current = drawing;
  const [panning, setPanning] = useState(false);
  const panningRef = useRef(false); panningRef.current = panning;
  const lastPanRef = useRef({ x: 0, y: 0 });

  const [selRect, setSelRect] = useState<SelRect | null>(null);
  const selRectRef = useRef<SelRect | null>(null); selRectRef.current = selRect;
  const [marqueeActive, setMarqueeActive] = useState<Marquee | null>(null);
  const marqueeRef = useRef<Marquee | null>(null); marqueeRef.current = marqueeActive;
  const [moveDrag, setMoveDrag] = useState<MoveDrag | null>(null);
  const moveDragRef = useRef<MoveDrag | null>(null); moveDragRef.current = moveDrag;

  // 光标圆追踪（画笔/橡皮/超级橡皮/吸管）
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);
  const showCircleCursor = tool === "brush" || tool === "eraser" || tool === "superEraser" || tool === "eyedropper";

  const historyRef = useRef<ImageData[]>([]);
  const MAX_HISTORY = 30;

  // ==================== Coordinate ====================

  /** screen→canvas pixel (container-relative, no double-offset bug) */
  const screenToCanvas = useCallback((cx: number, cy: number) => {
    if (!containerRef.current || !imgSize) return null;
    const el = containerRef.current;
    const rect = el.getBoundingClientRect();
    const sx = cx - rect.left - el.clientLeft, sy = cy - rect.top - el.clientTop;
    const x = (sx - offset.x) / displayScale, y = (sy - offset.y) / displayScale;
    const ix = Math.floor(x), iy = Math.floor(y);
    if (ix < 0 || ix >= imgSize.w || iy < 0 || iy >= imgSize.h) return null;
    return { x: ix, y: iy };
  }, [offset, displayScale, imgSize]);

  const screenToCanvasClamped = useCallback((cx: number, cy: number) => {
    if (!containerRef.current || !imgSize) return null;
    const el = containerRef.current;
    const rect = el.getBoundingClientRect();
    const sx = cx - rect.left - el.clientLeft, sy = cy - rect.top - el.clientTop;
    return { x: Math.max(0, Math.min(imgSize.w - 1, Math.floor((sx - offset.x) / displayScale))), y: Math.max(0, Math.min(imgSize.h - 1, Math.floor((sy - offset.y) / displayScale))) };
  }, [offset, displayScale, imgSize]);

  // ==================== History ====================

  const pushHistory = useCallback(() => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (!ctx || !imgSize) return;
    const id = ctx.getImageData(0, 0, imgSize.w, imgSize.h);
    historyRef.current.push(new ImageData(new Uint8ClampedArray(id.data), id.width, id.height));
    if (historyRef.current.length > MAX_HISTORY) historyRef.current.shift();
  }, [imgSize]);

  const handleUndo = useCallback(() => {
    const h = historyRef.current;
    if (h.length <= 1 || !imgSize) return;
    h.pop();
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (ctx) ctx.putImageData(h[h.length - 1]!, 0, 0);
  }, [imgSize]);

  // ==================== Draw ====================

  const drawAt = useCallback((px: number, py: number) => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (!ctx || !imgSize) return;
    const isBrush = toolRef.current === "brush";
    let rr = 0, gg = 0, bb = 0;
    if (isBrush) {
      const m = String(brushColor).match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
      if (m) { rr = parseInt(m[1], 16); gg = parseInt(m[2], 16); bb = parseInt(m[3], 16); }
      else { const tmp = document.createElement("canvas"); tmp.width = tmp.height = 1; const tctx = tmp.getContext("2d");
        if (tctx) { tctx.fillStyle = String(brushColor); tctx.fillRect(0, 0, 1, 1); const d = tctx.getImageData(0, 0, 1, 1).data; rr = d[0]; gg = d[1]; bb = d[2]; } }
    }
    const data = ctx.getImageData(0, 0, imgSize.w, imgSize.h);
    const cx = px + 0.5, cy = py + 0.5;
    const radius = (isBrush ? brushSizeRef.current : eraserSizeRef.current) / 2;
    const r2 = radius * radius, rad = Math.ceil(radius);
    const square = brushShapeRef.current === "square";
    for (let iy = Math.max(0, py - rad); iy <= Math.min(imgSize.h - 1, py + rad); iy++)
      for (let ix = Math.max(0, px - rad); ix <= Math.min(imgSize.w - 1, px + rad); ix++) {
        const inShape = square
          ? Math.abs(ix + 0.5 - cx) <= radius && Math.abs(iy + 0.5 - cy) <= radius
          : (ix + 0.5 - cx) ** 2 + (iy + 0.5 - cy) ** 2 <= r2;
        if (inShape) {
          const i = (iy * imgSize.w + ix) * 4;
          if (isBrush) { data.data[i] = rr; data.data[i + 1] = gg; data.data[i + 2] = bb; data.data[i + 3] = 255; }
          else data.data[i + 3] = 0;
        }
      }
    ctx.putImageData(data, 0, 0);
    ctx.globalCompositeOperation = "source-over";
  }, [brushColor, imgSize]);

  const superEraserAt = useCallback((px: number, py: number) => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (!ctx || !imgSize) return;
    const data = ctx.getImageData(0, 0, imgSize.w, imgSize.h);
    const { w, h } = imgSize;
    const idx = (py * w + px) * 4;
    const r0 = data.data[idx], g0 = data.data[idx + 1], b0 = data.data[idx + 2];
    if (data.data[idx + 3] === 0) return;
    const tol = superToleranceRef.current, tol2 = tol * tol;
    const dist2 = (r1: number, g1: number, b1: number) => (r1 - r0) ** 2 + (g1 - g0) ** 2 + (b1 - b0) ** 2;
    const visited = new Uint8Array(w * h);
    visited[py * w + px] = 1;
    const stack: [number, number][] = [[px, py]];
    const dx = [0, 1, 0, -1], dy = [-1, 0, 1, 0];
    while (stack.length) {
      const [x, y] = stack.pop()!;
      data.data[(y * w + x) * 4 + 3] = 0;
      for (let k = 0; k < 4; k++) {
        const nx = x + dx[k], ny = y + dy[k];
        if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
        const ni = ny * w + nx;
        if (visited[ni] || data.data[ni * 4 + 3] === 0) continue;
        if (dist2(data.data[ni * 4], data.data[ni * 4 + 1], data.data[ni * 4 + 2]) <= tol2) { visited[ni] = 1; stack.push([nx, ny]); }
      }
    }
    ctx.putImageData(data, 0, 0);
  }, [imgSize]);

  // ==================== Contrast (全局调整) ====================

  const handleContrastStart = useCallback(() => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (!ctx || !imgSize) return;
    contrastBaselineRef.current = ctx.getImageData(0, 0, imgSize.w, imgSize.h);
  }, [imgSize]);

  const applyContrast = useCallback((factor: number) => {
    const baseline = contrastBaselineRef.current;
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (!ctx || !baseline) return;
    const data = new ImageData(new Uint8ClampedArray(baseline.data), baseline.width, baseline.height);
    const clamp = (v: number) => v < 0 ? 0 : v > 255 ? 255 : Math.round(v);
    for (let i = 0; i < data.data.length; i += 4) {
      if (data.data[i + 3] === 0) continue;
      data.data[i] = clamp((data.data[i]! - 128) * factor + 128);
      data.data[i + 1] = clamp((data.data[i + 1]! - 128) * factor + 128);
      data.data[i + 2] = clamp((data.data[i + 2]! - 128) * factor + 128);
    }
    ctx.putImageData(data, 0, 0);
  }, []);

  const handleContrastEnd = useCallback(() => {
    pushHistory();
    contrastBaselineRef.current = null;
    setContrast(1.0);
  }, [pushHistory]);

  // ==================== SelectMove ====================

  const commitSelectMove = useCallback((sel: SelRect, dix: number, diy: number) => {
    const canvas = canvasRef.current; const ctx = canvas?.getContext("2d");
    if (!ctx || !imgSize) return;
    const nx = Math.max(0, Math.min(sel.x + dix, imgSize.w - sel.w));
    const ny = Math.max(0, Math.min(sel.y + diy, imgSize.h - sel.h));
    if (nx === sel.x && ny === sel.y) return;
    pushHistory();
    const full = ctx.getImageData(0, 0, imgSize.w, imgSize.h);
    const chunk = ctx.getImageData(sel.x, sel.y, sel.w, sel.h);
    for (let j = 0; j < sel.h; j++) for (let i = 0; i < sel.w; i++) { const di = ((sel.y + j) * imgSize.w + (sel.x + i)) * 4; full.data[di] = full.data[di + 1] = full.data[di + 2] = full.data[di + 3] = 0; }
    for (let j = 0; j < sel.h; j++) for (let i = 0; i < sel.w; i++) {
      const dx = nx + i, dy = ny + j;
      if (dx < 0 || dx >= imgSize.w || dy < 0 || dy >= imgSize.h) continue;
      const si = (j * sel.w + i) * 4, di = (dy * imgSize.w + dx) * 4;
      full.data[di] = chunk.data[si]; full.data[di + 1] = chunk.data[si + 1]; full.data[di + 2] = chunk.data[si + 2]; full.data[di + 3] = chunk.data[si + 3];
    }
    ctx.putImageData(full, 0, 0);
    setSelRect({ x: nx, y: ny, w: sel.w, h: sel.h });
  }, [imgSize, pushHistory]);

  const clearSelectUi = useCallback(() => { setSelRect(null); setMarqueeActive(null); setMoveDrag(null); }, []);
  const switchTool = useCallback((next: Tool) => { if (next !== "selectMove") clearSelectUi(); setTool(next); }, [clearSelectUi]);

  // ==================== SVG Cursors ====================

  const eraserCursor = useCallback(() => {
    const d = Math.min(128, Math.max(2, Math.ceil(eraserSize * displayScale))), r = d / 2;
    const shapeEl = brushShape === "square"
      ? `<rect x="${1}" y="${1}" width="${d - 2}" height="${d - 2}" rx="2" fill="none" stroke="#333" stroke-width="2"/>`
      : `<circle cx="${r}" cy="${r}" r="${r - 1}" fill="none" stroke="#333" stroke-width="2"/>`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${d}" height="${d}" viewBox="0 0 ${d} ${d}">${shapeEl}</svg>`;
    return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}") ${r} ${r}, cell`;
  }, [eraserSize, displayScale, brushShape]);

  const brushCursor = useCallback(() => {
    const d = Math.min(128, Math.max(2, Math.ceil(brushSize * displayScale))), r = d / 2;
    const col = String(brushColor);
    const shapeEl = brushShape === "square"
      ? `<rect x="${1}" y="${1}" width="${d - 2}" height="${d - 2}" rx="2" fill="${col}" fill-opacity="0.15" stroke="${col}" stroke-opacity="0.75" stroke-width="2"/>`
      : `<circle cx="${r}" cy="${r}" r="${Math.max(1, r - 1)}" fill="${col}" fill-opacity="0.15" stroke="${col}" stroke-opacity="0.75" stroke-width="2"/>`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${d}" height="${d}" viewBox="0 0 ${d} ${d}">${shapeEl}</svg>`;
    return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}") ${r} ${r}, cell`;
  }, [brushSize, displayScale, brushColor, brushShape]);

  // ==================== Image Load ====================

  useEffect(() => {
    if (!src) { setImgSize(null); setLoading(true); return; }
    setImgSize(null); setLoading(true);
    const img = new Image(); img.crossOrigin = "anonymous";
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height;
      setImgSize({ w, h });
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h); ctx.drawImage(img, 0, 0);
      const id = ctx.getImageData(0, 0, w, h);
      historyRef.current = [new ImageData(new Uint8ClampedArray(id.data), id.width, id.height)];
      setLoading(false);
    };
    img.onerror = () => setLoading(false);
    img.src = src;
  }, [src]);

  // ==================== ResizeObserver ====================

  useEffect(() => {
    if (!containerRef.current || !imgSize) return;
    const el = containerRef.current;
    const updateFitScale = () => {
      const cw = el.clientWidth, ch = el.clientHeight;
      if (cw <= 0 || ch <= 0) return;
      const s = Math.min(cw / imgSize.w, ch / imgSize.h);
      const z = zoomFactorRef.current, ds = s * z;
      fitScaleRef.current = s;
      const off = { x: (cw - imgSize.w * ds) / 2, y: (ch - imgSize.h * ds) / 2 };
      offsetRef.current = off;
      setFitScale(s); setOffset(off);
    };
    updateFitScale();
    const ro = new ResizeObserver(updateFitScale);
    ro.observe(el);
    return () => ro.disconnect();
  }, [imgSize]);

  // ==================== Pointer Events (on container) ====================

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (!imgSize) return;
    e.preventDefault();
    if (e.button === 2) { setPanning(true); panningRef.current = true; lastPanRef.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); return; }
    if (e.button === 0 && toolRef.current === "pan") { setPanning(true); panningRef.current = true; lastPanRef.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId); return; }
    if (e.button === 0 && toolRef.current === "selectMove") {
      const p = screenToCanvas(e.clientX, e.clientY);
      if (!p) return;
      const sel = selRectRef.current;
      if (sel && pointInSelRect(p.x, p.y, sel)) { setMoveDrag({ scx: e.clientX, scy: e.clientY, dix: 0, diy: 0 }); e.currentTarget.setPointerCapture(e.pointerId); return; }
      setSelRect(null); setMarqueeActive({ ax: p.x, ay: p.y, bx: p.x, by: p.y }); e.currentTarget.setPointerCapture(e.pointerId); return;
    }
    if (e.button === 0 && toolRef.current !== "pan") {
      const pt = screenToCanvas(e.clientX, e.clientY);
      if (!pt) return;
      if (toolRef.current === "eyedropper") {
        const c = canvasRef.current, ctx = c?.getContext("2d");
        if (!ctx) return;
        const d = ctx.getImageData(pt.x, pt.y, 1, 1).data;
        if (d[3] > 0) { setBrushColor(`#${[d[0]!, d[1]!, d[2]!].map(v => v.toString(16).padStart(2, "0")).join("")}`); setTool("brush"); }
        return;
      }
      if (toolRef.current === "superEraser") { pushHistory(); superEraserAt(pt.x, pt.y); }
      else { pushHistory(); setDrawing(true); drawingRef.current = true; drawAt(pt.x, pt.y); }
      e.currentTarget.setPointerCapture(e.pointerId);
    }
  }, [imgSize, screenToCanvas, drawAt, superEraserAt, pushHistory]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    // 光标圆追踪（始终更新，不分工具）
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    }
    if (panningRef.current) { e.preventDefault(); const dx = e.clientX - lastPanRef.current.x, dy = e.clientY - lastPanRef.current.y; lastPanRef.current = { x: e.clientX, y: e.clientY }; setOffset(off => { const n = { x: off.x + dx, y: off.y + dy }; offsetRef.current = n; return n; }); return; }
    if (marqueeRef.current) { e.preventDefault(); const p = screenToCanvasClamped(e.clientX, e.clientY); if (p) setMarqueeActive(m => m ? { ...m, bx: p.x, by: p.y } : null); return; }
    if (moveDragRef.current) { e.preventDefault(); setMoveDrag(m => m ? { ...m, dix: Math.round((e.clientX - m.scx) / displayScale), diy: Math.round((e.clientY - m.scy) / displayScale) } : null); return; }
    if (drawingRef.current && imgSize && toolRef.current !== "superEraser") { e.preventDefault(); const pt = screenToCanvas(e.clientX, e.clientY); if (pt) drawAt(pt.x, pt.y); }
  }, [screenToCanvas, screenToCanvasClamped, drawAt, displayScale, imgSize]);

  const handlePointerUp = useCallback((e: React.PointerEvent) => {
    if (e.button === 2 || toolRef.current === "pan") { setPanning(false); panningRef.current = false; try { e.currentTarget.releasePointerCapture(e.pointerId); } catch {} return; }
    if (e.button === 0) {
      setDrawing(false); drawingRef.current = false;
      const mq = marqueeRef.current;
      if (mq) { const x0 = Math.min(mq.ax, mq.bx), y0 = Math.min(mq.ay, mq.by), x1 = Math.max(mq.ax, mq.bx), y1 = Math.max(mq.ay, mq.by), w = x1 - x0 + 1, h = y1 - y0 + 1; if (w >= 2 && h >= 2) setSelRect({ x: x0, y: y0, w, h }); setMarqueeActive(null); try { e.currentTarget.releasePointerCapture(e.pointerId); } catch {} return; }
      const md = moveDragRef.current, sel = selRectRef.current;
      if (md && sel) { if (md.dix !== 0 || md.diy !== 0) commitSelectMove(sel, md.dix, md.diy); setMoveDrag(null); }
      try { e.currentTarget.releasePointerCapture(e.pointerId); } catch {}
    }
  }, [commitSelectMove]);

  const handlePointerLeave = useCallback(() => { setDrawing(false); drawingRef.current = false; setPanning(false); panningRef.current = false; setMarqueeActive(null); setMoveDrag(null); setCursorPos(null); }, []);

  useEffect(() => { if (!drawing && !panning) return; const onUp = () => { setDrawing(false); drawingRef.current = false; setPanning(false); panningRef.current = false; }; window.addEventListener("pointerup", onUp); window.addEventListener("pointercancel", onUp); return () => { window.removeEventListener("pointerup", onUp); window.removeEventListener("pointercancel", onUp); }; }, [drawing, panning]);
  useEffect(() => { if (!marqueeActive && !moveDrag) return; const onCancel = () => { setMarqueeActive(null); setMoveDrag(null); }; window.addEventListener("pointercancel", onCancel); return () => window.removeEventListener("pointercancel", onCancel); }, [marqueeActive, moveDrag]);

  // ==================== Zoom (wheel on container) ====================

  useEffect(() => { const el = containerRef.current; if (!el || !imgSize) return; const onWheel = (e: WheelEvent) => { e.preventDefault(); const rect = el.getBoundingClientRect(), cx = e.clientX - rect.left - el.clientLeft, cy = e.clientY - rect.top - el.clientTop, delta = -Math.sign(e.deltaY) * 0.15, fit = fitScaleRef.current, z = zoomFactorRef.current, zNew = Math.max(0.25, Math.min(4, z * (1 + delta))), scaleOld = fit * z, scaleNew = fit * zNew; if (scaleOld > 0) { const ratio = scaleNew / scaleOld, off = offsetRef.current, offNew = { x: cx - (cx - off.x) * ratio, y: cy - (cy - off.y) * ratio }; setOffset(offNew); offsetRef.current = offNew; } setZoomFactor(zNew); }; el.addEventListener("wheel", onWheel, { passive: false }); return () => el.removeEventListener("wheel", onWheel); }, [imgSize]);

  // ==================== Keyboard ====================

  // Ctrl+Z undo
  useEffect(() => { if (!imgSize) return; const onKeyDown = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key === "z") { const t = e.target as HTMLElement; if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return; e.preventDefault(); handleUndo(); } }; window.addEventListener("keydown", onKeyDown); return () => window.removeEventListener("keydown", onKeyDown); }, [imgSize, handleUndo]);
  // Escape
  useEffect(() => { if (tool !== "selectMove") return; const onKeyDown = (e: KeyboardEvent) => { if (e.key !== "Escape") return; const t = e.target as HTMLElement; if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return; e.preventDefault(); clearSelectUi(); }; window.addEventListener("keydown", onKeyDown); return () => window.removeEventListener("keydown", onKeyDown); }, [tool, clearSelectUi]);
  // Arrow keys selectMove
  useEffect(() => { if (!imgSize || tool !== "selectMove") return; const onKeyDown = (e: KeyboardEvent) => { const t = e.target as HTMLElement; if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable) return; if (marqueeRef.current || moveDragRef.current) return; const sel = selRectRef.current; if (!sel) return; const code = e.code; if (code !== "ArrowUp" && code !== "ArrowDown" && code !== "ArrowLeft" && code !== "ArrowRight") return; if (e.ctrlKey || e.metaKey || e.altKey) return; const step = e.shiftKey ? 8 : 1; let dx = 0, dy = 0; if (code === "ArrowLeft") dx = -step; else if (code === "ArrowRight") dx = step; else if (code === "ArrowUp") dy = -step; else dy = step; e.preventDefault(); commitSelectMove(sel, dx, dy); }; window.addEventListener("keydown", onKeyDown); return () => window.removeEventListener("keydown", onKeyDown); }, [imgSize, tool, commitSelectMove]);

  // WASD pan
  useEffect(() => { if (!imgSize) return; const keys = new Set<string>(); let rafId = 0, last = performance.now(); const PAN_PX_PER_SEC = 520; const step = (now: number) => { rafId = requestAnimationFrame(step); const dt = Math.min((now - last) / 1000, 0.05); last = now; if (keys.size === 0) return; let dx = 0, dy = 0; if (keys.has("a")) dx -= PAN_PX_PER_SEC * dt; if (keys.has("d")) dx += PAN_PX_PER_SEC * dt; if (keys.has("w")) dy -= PAN_PX_PER_SEC * dt; if (keys.has("s")) dy += PAN_PX_PER_SEC * dt; if (dx === 0 && dy === 0) return; setOffset(off => { const n = { x: off.x + dx, y: off.y + dy }; offsetRef.current = n; return n; }); }; const targetOk = (el: EventTarget | null) => { const t = el as HTMLElement; if (!t) return true; if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return false; if (t.isContentEditable) return false; return true; }; const onKeyDown = (e: KeyboardEvent) => { if (!targetOk(e.target)) return; if (e.ctrlKey || e.metaKey || e.altKey) return; const c = e.code; if (c !== "KeyW" && c !== "KeyA" && c !== "KeyS" && c !== "KeyD") return; const k = c === "KeyW" ? "w" : c === "KeyA" ? "a" : c === "KeyS" ? "s" : "d"; keys.add(k); e.preventDefault(); }; const onKeyUp = (e: KeyboardEvent) => { const c = e.code; if (c === "KeyW") keys.delete("w"); else if (c === "KeyA") keys.delete("a"); else if (c === "KeyS") keys.delete("s"); else if (c === "KeyD") keys.delete("d"); }; window.addEventListener("keydown", onKeyDown); window.addEventListener("keyup", onKeyUp); window.addEventListener("blur", () => keys.clear()); rafId = requestAnimationFrame(step); return () => { window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp); window.removeEventListener("blur", () => keys.clear()); cancelAnimationFrame(rafId); }; }, [imgSize]);

  // ==================== Export ====================

  const handleExport = useCallback(() => { const c = canvasRef.current; if (!c) return; c.toBlob(b => { if (b && onExport) onExport(b); }, "image/png"); }, [onExport]);

  // ==================== Render ====================

  return (
    <div className="flex h-full min-h-0">
      {/* ===== 左侧工具栏 ===== */}
      <div className="w-[80px] flex-shrink-0 border-r border-line bg-bg-1 flex flex-col items-center py-2 gap-1">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTool(t.id)}
            title={t.label}
            className={`w-9 h-9 rounded flex flex-col items-center justify-center text-[15px] leading-none transition-colors ${
              tool === t.id
                ? "bg-acc text-white"
                : "text-txt-3 hover:text-txt-1 hover:bg-bg-3"
            }`}
          >
            {t.icon}
            <span className="text-[8px] mt-0.5 opacity-70 leading-none">{t.label}</span>
          </button>
        ))}

        {/* 对比度调整 */}
        {imgSize && (
          <div className="w-full px-1.5 space-y-1 border-t border-line pt-2 mt-1">
            <div className="text-[9px] text-txt-3 text-center">对比度</div>
            <input
              type="range"
              min={0}
              max={3}
              step={0.02}
              value={contrast}
              onChange={(e) => {
                const factor = Number(e.target.value);
                setContrast(factor);
                applyContrast(factor);
              }}
              onMouseDown={handleContrastStart}
              onMouseUp={handleContrastEnd}
              onTouchStart={handleContrastStart}
              onTouchEnd={handleContrastEnd}
              className="w-full h-2 accent-acc cursor-pointer"
            />
            <div className="text-[10px] text-txt-2 text-center">{contrast.toFixed(2)}</div>
          </div>
        )}

        {/* 工具参数 */}
        <div className="mt-auto w-full px-1.5 pb-2 space-y-1.5">
          {tool === "brush" && (
            <>
              <input
                type="color"
                value={brushColor}
                onChange={(e) => setBrushColor(e.target.value)}
                className="w-full h-6 rounded cursor-pointer border border-line bg-transparent p-0"
                title="颜色"
              />
              <div className="text-[9px] text-txt-3 text-center">画笔形状</div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setBrushShape("round")}
                  className={`flex-1 py-0.5 rounded flex items-center justify-center gap-0.5 text-[9px] transition-colors ${
                    brushShape === "round" ? "bg-acc text-white" : "text-txt-3 hover:text-txt-1 bg-bg-3"
                  }`}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="8"/></svg>
                  <span>圆形</span>
                </button>
                <button
                  type="button"
                  onClick={() => setBrushShape("square")}
                  className={`flex-1 py-0.5 rounded flex items-center justify-center gap-0.5 text-[9px] transition-colors ${
                    brushShape === "square" ? "bg-acc text-white" : "text-txt-3 hover:text-txt-1 bg-bg-3"
                  }`}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
                  <span>方形</span>
                </button>
              </div>
              <div className="text-[9px] text-txt-3 text-center">画笔大小</div>
              <input
                type="range"
                min={1}
                max={32}
                value={brushSize}
                onChange={(e) => setBrushSize(Number(e.target.value))}
                className="w-full h-2 accent-acc"
              />
              <div className="text-[10px] text-txt-2 text-center">{brushSize}px</div>
            </>
          )}
          {tool === "eraser" && (
            <>
              <div className="text-[9px] text-txt-3 text-center">画笔形状</div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setBrushShape("round")}
                  className={`flex-1 py-0.5 rounded flex items-center justify-center gap-0.5 text-[9px] transition-colors ${
                    brushShape === "round" ? "bg-acc text-white" : "text-txt-3 hover:text-txt-1 bg-bg-3"
                  }`}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="8"/></svg>
                  <span>圆形</span>
                </button>
                <button
                  type="button"
                  onClick={() => setBrushShape("square")}
                  className={`flex-1 py-0.5 rounded flex items-center justify-center gap-0.5 text-[9px] transition-colors ${
                    brushShape === "square" ? "bg-acc text-white" : "text-txt-3 hover:text-txt-1 bg-bg-3"
                  }`}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
                  <span>方形</span>
                </button>
              </div>
              <div className="text-[9px] text-txt-3 text-center">画笔大小</div>
              <input
                type="range"
                min={1}
                max={64}
                value={eraserSize}
                onChange={(e) => setEraserSize(Number(e.target.value))}
                className="w-full h-2 accent-acc"
              />
              <div className="text-[10px] text-txt-2 text-center">{eraserSize}px</div>
            </>
          )}
          {tool === "superEraser" && (
            <>
              <div className="text-[9px] text-txt-3 text-center">容差</div>
              <div className="flex items-center justify-center gap-0.5">
                <button
                  type="button"
                  onClick={() => setBrushShape("round")}
                  title="圆形"
                  className={`w-5 h-5 rounded-full flex items-center justify-center transition-colors ${
                    brushShape === "round" ? "bg-acc text-white" : "text-txt-3 hover:text-txt-1"
                  }`}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="8"/></svg>
                </button>
                <button
                  type="button"
                  onClick={() => setBrushShape("square")}
                  title="方形"
                  className={`w-5 h-5 rounded flex items-center justify-center transition-colors ${
                    brushShape === "square" ? "bg-acc text-white" : "text-txt-3 hover:text-txt-1"
                  }`}
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
                </button>
              </div>
              <input
                type="range"
                min={1}
                max={100}
                value={superTolerance}
                onChange={(e) => setSuperTolerance(Number(e.target.value))}
                className="w-full h-2"
              />
              <div className="text-[10px] text-txt-2 text-center">{superTolerance}</div>
            </>
          )}
        </div>
      </div>

      {/* ===== 右侧画布区 ===== */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        {/* 顶部状态栏 */}
        <div className="h-8 px-3 flex items-center justify-between border-b border-line bg-bg-1 flex-shrink-0">
          <span className="text-[11px] text-txt-3">
            {imgSize ? `${Math.round(displayScale * 100)}% · ${imgSize.w}×${imgSize.h}px` : "加载中..."}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleExport}
              className="px-2 h-6 rounded text-[10.5px] bg-bg-3 text-txt-2 hover:text-txt-1 border border-line transition-colors"
            >
              保存
            </button>
            {onReset && (
              <button
                onClick={onReset}
                className="px-2 h-6 rounded text-[10.5px] bg-bg-3 text-txt-2 hover:text-txt-1 border border-line transition-colors"
              >
                重置
              </button>
            )}
          </div>
        </div>

        {/* 画布容器 */}
        <div
          ref={containerRef}
          className="flex-1 min-h-0 overflow-hidden bg-[#1a1a2e] relative"
          style={{ cursor: tool === "pan" ? "grab" : tool === "selectMove" ? "default" : showCircleCursor ? "none" : "crosshair" }}
          onContextMenu={(e) => e.preventDefault()}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerLeave}
        >
          {/* 棋盘格背景 */}
          <div
            className="absolute inset-0"
            style={{
              backgroundImage:
                "linear-gradient(45deg, #2a2a3e 25%, transparent 25%), linear-gradient(-45deg, #2a2a3e 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #2a2a3e 75%), linear-gradient(-45deg, transparent 75%, #2a2a3e 75%)",
              backgroundSize: "20px 20px",
              backgroundPosition: "0 0, 0 10px, 10px -10px, -10px 0px",
            }}
          />

          {/* Canvas — pointerEvents:none, 所有事件由 container 统一处理 */}
          <canvas
            ref={canvasRef}
            style={{
              position: "absolute",
              left: `${offset.x}px`,
              top: `${offset.y}px`,
              width: `${imgSize ? Math.max(imgSize.w, 1) * displayScale : 0}px`,
              height: `${imgSize ? Math.max(imgSize.h, 1) * displayScale : 0}px`,
              imageRendering: "pixelated",
              pointerEvents: "none",
              visibility: loading ? "hidden" : "visible",
            }}
          />

          {/* 框选覆盖层 — marqueeActive 拖拽中 */}
          {marqueeActive && imgSize && (() => {
            const x0 = Math.min(marqueeActive.ax, marqueeActive.bx);
            const y0 = Math.min(marqueeActive.ay, marqueeActive.by);
            const x1 = Math.max(marqueeActive.ax, marqueeActive.bx);
            const y1 = Math.max(marqueeActive.ay, marqueeActive.by);
            return (
              <div
                className="absolute pointer-events-none border border-dashed border-white/80 bg-white/5"
                style={{
                  left: `${offset.x + x0 * displayScale}px`,
                  top: `${offset.y + y0 * displayScale}px`,
                  width: `${(x1 - x0 + 1) * displayScale}px`,
                  height: `${(y1 - y0 + 1) * displayScale}px`,
                }}
              />
            );
          })()}

          {/* 框选覆盖层 — selRect 已确认 */}
          {selRect && tool === "selectMove" && imgSize && (
            <div
              className="absolute pointer-events-none border border-acc/80 bg-acc/5"
              style={{
                left: `${offset.x + selRect.x * displayScale}px`,
                top: `${offset.y + selRect.y * displayScale}px`,
                width: `${selRect.w * displayScale}px`,
                height: `${selRect.h * displayScale}px`,
              }}
            />
          )}

          {/* 光标覆盖层（画笔/橡皮/超级橡皮/吸管工具） */}
          {showCircleCursor && cursorPos && !panning && imgSize && (() => {
            const p = cursorPos!;
            const size = tool === "eraser" ? eraserSize : tool === "superEraser" ? superTolerance / 3 + 2 : tool === "eyedropper" ? 2 : brushSize;
            const borderColor = tool === "eraser" ? "rgba(255,255,255,0.6)" : tool === "superEraser" ? "rgba(255,200,50,0.7)" : tool === "eyedropper" ? "rgba(255,255,255,0.7)" : brushColor + "cc";
            const bgColor = tool === "eraser" ? "transparent" : tool === "superEraser" ? "transparent" : tool === "eyedropper" ? "transparent" : brushColor + "18";
            const isSquare = brushShape === "square" && tool !== "eyedropper";
            return (
              <div
                className={`pointer-events-none absolute border ${isSquare ? "rounded-[2px]" : "rounded-full"}`}
                style={{
                  width: `${size * displayScale}px`,
                  height: `${size * displayScale}px`,
                  left: `${p.x}px`,
                  top: `${p.y}px`,
                  transform: "translate(-50%, -50%)",
                  borderColor,
                  backgroundColor: bgColor,
                  borderWidth: "1.5px",
                }}
              >
                {/* 中心准心点 */}
                <div
                  className="absolute rounded-full"
                  style={{
                    width: "3px",
                    height: "3px",
                    left: "50%",
                    top: "50%",
                    transform: "translate(-50%, -50%)",
                    backgroundColor: borderColor,
                  }}
                />
              </div>
            );
          })()}

          {/* Loading */}
          {loading && (
            <div className="absolute inset-0 grid place-items-center text-txt-2 text-[12px]">
              Loading...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * MaskCanvas — 交互编辑 mask 涂抹画布
 *
 * 架构（参考 PixelEditor）：
 * - container 处理所有 pointer 事件
 * - canvas pointer-events:none
 * - 原图渲染到 canvas，mask 数据存储在独立 Uint8Array
 * - 红色半透明叠加显示编辑区域
 * - 支持画笔/橡皮，导出 mask 为 PNG Blob
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  src: string;
  onMaskReady?: (blob: Blob) => void;
  /** 画笔大小，外部可控 */
  brushSize: number;
}

export function MaskCanvas({ src, onMaskReady, brushSize }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);


  const brushSizeRef = useRef(brushSize);
  brushSizeRef.current = brushSize;

  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const imgSizeRef = useRef<{ w: number; h: number } | null>(null);
  imgSizeRef.current = imgSize;

  // mask 数据：0=黑色(保留), 255=白色(编辑)
  const maskRef = useRef<Uint8Array | null>(null);
  // 原图 ImageData 快照
  const origImageRef = useRef<ImageData | null>(null);
  // 当前 canvas 显示的 ImageData（原图 + mask 叠加）
  const displayRef = useRef<ImageData | null>(null);

  const [fitScale, setFitScale] = useState(1);
  const fitScaleRef = useRef(1);
  fitScaleRef.current = fitScale;
  const [zoomFactor, setZoomFactor] = useState(1);
  const zoomFactorRef = useRef(1);
  zoomFactorRef.current = zoomFactor;
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const offsetRef = useRef({ x: 0, y: 0 });
  offsetRef.current = offset;
  const displayScale = fitScale * zoomFactor;

  const [drawing, setDrawing] = useState(false);
  const drawingRef = useRef(false);
  drawingRef.current = drawing;
  const [loading, setLoading] = useState(true);

  const [hasMask, setHasMask] = useState(false);

  // 历史栈（用于撤销）
  const historyRef = useRef<Uint8Array[]>([]);
  const MAX_HISTORY = 30;

  // 光标圆位置
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);

  // ==================== Coordinate ====================

  const screenToCanvas = useCallback(
    (cx: number, cy: number) => {
      if (!containerRef.current || !imgSize) return null;
      const rect = containerRef.current.getBoundingClientRect();
      const sx = cx - rect.left - containerRef.current.clientLeft;
      const sy = cy - rect.top - containerRef.current.clientTop;
      const x = Math.floor((sx - offset.x) / displayScale);
      const y = Math.floor((sy - offset.y) / displayScale);
      if (x < 0 || x >= imgSize.w || y < 0 || y >= imgSize.h) return null;
      return { x, y };
    },
    [offset, displayScale, imgSize],
  );

  // ==================== Render Display ====================

  /** 将 mask 数据叠加到原图上渲染 */
  const renderDisplay = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!ctx || !origImageRef.current || !maskRef.current || !imgSize) return;
    const { w, h } = imgSize;

    const data = new Uint8ClampedArray(origImageRef.current.data);
    const mask = maskRef.current;

    // mask 白色区域叠加红色半透明
    for (let i = 0; i < w * h; i++) {
      const idx = i * 4;
      const m = mask[i]!;
      if (m > 0) {
        const alpha = m / 255;
        // red tint: blend red with original
        const r0 = data[idx]!;
        const g0 = data[idx + 1]!;
        const b0 = data[idx + 2]!;
        // Keep original, just add red overlay tint
        data[idx] = Math.min(255, Math.round(r0 * (1 - alpha * 0.6) + 255 * alpha * 0.6));
        data[idx + 1] = Math.round(g0 * (1 - alpha * 0.5));
        data[idx + 2] = Math.round(b0 * (1 - alpha * 0.5));
      }
    }

    const id = new ImageData(data, w, h);
    displayRef.current = id;
    ctx.putImageData(id, 0, 0);
  }, [imgSize]);

  // ==================== Export Mask ====================

  const exportMask = useCallback((): Promise<Blob | null> => {
    const mask = maskRef.current;
    if (!mask || !imgSize) return Promise.resolve(null);
    const { w, h } = imgSize;
    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = w;
    exportCanvas.height = h;
    const ectx = exportCanvas.getContext("2d");
    if (!ectx) return Promise.resolve(null);
    const data = ectx.createImageData(w, h);
    for (let i = 0; i < w * h; i++) {
      const idx = i * 4;
      const v = mask[i]!;
      data.data[idx] = v;
      data.data[idx + 1] = v;
      data.data[idx + 2] = v;
      data.data[idx + 3] = 255;
    }
    ectx.putImageData(data, 0, 0);

    return new Promise<Blob>((resolve) => {
      exportCanvas.toBlob((b) => resolve(b!), "image/png");
    });
  }, [imgSize]);

  // ==================== History ====================

  const pushHistory = useCallback(() => {
    if (!maskRef.current || !imgSize) return;
    const copy = new Uint8Array(maskRef.current);
    historyRef.current.push(copy);
    if (historyRef.current.length > MAX_HISTORY) historyRef.current.shift();
  }, [imgSize]);

  const handleUndo = useCallback(() => {
    const h = historyRef.current;
    if (h.length <= 1 || !imgSize) return;
    h.pop();
    maskRef.current = new Uint8Array(h[h.length - 1]!);
    renderDisplay();
    const hasMaskNow = maskRef.current.some((v) => v > 0);
    setHasMask(hasMaskNow);
    if (onMaskReady) {
      exportMask().then((blob) => {
        if (blob) onMaskReady(blob);
      });
    }
  }, [imgSize, renderDisplay, exportMask, onMaskReady]);

  // ==================== Draw Mask ====================

  const drawMaskAt = useCallback(
    (px: number, py: number) => {
      if (!maskRef.current || !imgSize) return;
      const { w, h } = imgSize;
      const val = 255;
      const radius = brushSizeRef.current / 2;
      const rad = Math.ceil(radius);
      const r2 = radius * radius;

      const mask = maskRef.current;
      for (let dy = -rad; dy <= rad; dy++) {
        for (let dx = -rad; dx <= rad; dx++) {
          if (dx * dx + dy * dy > r2) continue;
          const ix = px + dx;
          const iy = py + dy;
          if (ix < 0 || ix >= w || iy < 0 || iy >= h) continue;
          mask[iy * w + ix] = val;
        }
      }
      renderDisplay();
    },
    [imgSize, renderDisplay],
  );

  // ==================== Image Load ====================

  useEffect(() => {
    if (!src) {
      setImgSize(null);
      setLoading(true);
      return;
    }
    setImgSize(null);
    setLoading(true);
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      setImgSize({ w, h });
      imgSizeRef.current = { w, h };
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0);
      const orig = ctx.getImageData(0, 0, w, h);
      origImageRef.current = orig;
      displayRef.current = orig;
      // 初始化 mask
      const mask = new Uint8Array(w * h);
      maskRef.current = mask;
      historyRef.current = [new Uint8Array(mask)];
      setHasMask(false);
      setLoading(false);
    };
    img.onerror = () => setLoading(false);
    img.src = src;
  }, [src]);

  // ==================== ResizeObserver ====================

  useEffect(() => {
    if (!containerRef.current || !imgSize) return;
    const el = containerRef.current;
    const updateFit = () => {
      const cw = el.clientWidth;
      const ch = el.clientHeight;
      if (cw <= 0 || ch <= 0) return;
      const s = Math.min(cw / imgSize.w, ch / imgSize.h);
      const z = zoomFactorRef.current;
      const ds = s * z;
      fitScaleRef.current = s;
      const off = { x: (cw - imgSize.w * ds) / 2, y: (ch - imgSize.h * ds) / 2 };
      offsetRef.current = off;
      setFitScale(s);
      setOffset(off);
    };
    updateFit();
    const ro = new ResizeObserver(updateFit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [imgSize]);

  // ==================== Pointer Events ====================

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (!imgSize || e.button !== 0) return;
      e.preventDefault();
      const pt = screenToCanvas(e.clientX, e.clientY);
      if (!pt) return;
      pushHistory();
      setDrawing(true);
      drawingRef.current = true;
      drawMaskAt(pt.x, pt.y);
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [imgSize, screenToCanvas, drawMaskAt, pushHistory],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      }
      if (drawingRef.current && imgSize) {
        e.preventDefault();
        const pt = screenToCanvas(e.clientX, e.clientY);
        if (pt) drawMaskAt(pt.x, pt.y);
      }
    },
    [screenToCanvas, drawMaskAt, imgSize],
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      setDrawing(false);
      drawingRef.current = false;
      const hasMaskNow = maskRef.current?.some((v) => v > 0) ?? false;
      setHasMask(hasMaskNow);
      // 每次提笔都导出最新的 mask blob 给父组件
      if (onMaskReady) {
        exportMask().then((blob) => {
          if (blob) onMaskReady(blob);
        });
      }
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {}
    },
    [exportMask, onMaskReady],
  );

  const handlePointerLeave = useCallback(() => {
    setDrawing(false);
    drawingRef.current = false;
    setCursorPos(null);
  }, []);

  // Window-level cleanup for stuck pointer
  useEffect(() => {
    if (!drawing) return;
    const onUp = () => {
      setDrawing(false);
      drawingRef.current = false;
    };
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [drawing]);

  // ==================== Zoom ====================

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !imgSize) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left - el.clientLeft;
      const cy = e.clientY - rect.top - el.clientTop;
      const delta = -Math.sign(e.deltaY) * 0.15;
      const z = zoomFactorRef.current;
      const zNew = Math.max(0.25, Math.min(4, z * (1 + delta)));
      const fit = fitScaleRef.current;
      const scaleOld = fit * z;
      const scaleNew = fit * zNew;
      if (scaleOld > 0) {
        const ratio = scaleNew / scaleOld;
        const off = offsetRef.current;
        const offNew = { x: cx - (cx - off.x) * ratio, y: cy - (cy - off.y) * ratio };
        setOffset(offNew);
        offsetRef.current = offNew;
      }
      setZoomFactor(zNew);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [imgSize]);

  // ==================== Keyboard ====================

  // Ctrl+Z undo
  useEffect(() => {
    if (!imgSize) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        const t = e.target as HTMLElement;
        if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return;
        e.preventDefault();
        handleUndo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [imgSize, handleUndo]);

  // Notify parent when mask changes
  useEffect(() => {
    if (hasMask && onMaskReady) {
      exportMask().then((blob) => {
        if (blob) onMaskReady(blob);
      });
    }
  }, [hasMask, exportMask, onMaskReady]);

  // ==================== Render ====================

  const cursorSize = brushSize * displayScale;

  return (
    <div className="flex h-full min-h-0">
      {/* 左侧工具栏 */}
      <div className="w-[80px] flex-shrink-0 border-r border-line bg-bg-1 flex flex-col items-center py-3 gap-2">
        <button
          title="画笔 - 涂抹编辑区域"
          className="w-9 h-9 rounded flex flex-col items-center justify-center transition-colors bg-acc text-white"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18.4 2.6a2.1 2.1 0 013 3L12 15l-5 5-3 1 1-3 5-5z M10 12l4 4" />
          </svg>
          <span className="text-[8px] mt-0.5 opacity-70">画笔</span>
        </button>

        <button
          onClick={handleUndo}
          title="撤销 (Ctrl+Z)"
          disabled={historyRef.current.length <= 1}
          className="w-9 h-9 rounded flex flex-col items-center justify-center text-txt-3 hover:text-txt-1 hover:bg-bg-3 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 10h10a5 5 0 015 5v0a5 5 0 01-5 5H11 M7 6l-4 4 4 4" />
          </svg>
          <span className="text-[8px] mt-0.5 opacity-70">撤销</span>
        </button>

        {/* 图例 */}
        <div className="mt-auto w-full px-2 pb-2 text-center">
          <div className="flex items-center gap-1 mb-1 justify-center">
            <div className="w-3 h-3 rounded-sm bg-white/20 border border-white/30" />
            <span className="text-[8px] text-txt-3">编辑区</span>
          </div>
          <div className="flex items-center gap-1 justify-center">
            <div className="w-3 h-3 rounded-sm bg-bg-1 border border-line" />
            <span className="text-[8px] text-txt-3">保留区</span>
          </div>
        </div>
      </div>

      {/* 画布容器 */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 overflow-hidden bg-[#1a1a2e] relative"
        style={{ cursor: "none" }}
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

        {/* Canvas */}
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

        {/* 光标指示器 */}
        {cursorPos && !drawing && imgSize && (
          <div
            className="pointer-events-none absolute rounded-full border-2 border-white/60"
            style={{
              width: `${cursorSize}px`,
              height: `${cursorSize}px`,
              left: `${cursorPos.x}px`,
              top: `${cursorPos.y}px`,
              transform: "translate(-50%, -50%)",
              backgroundColor: "rgba(255,100,100,0.15)",
            }}
          />
        )}

        {/* Loading */}
        {loading && (
          <div className="absolute inset-0 grid place-items-center text-txt-2 text-[12px]">
            Loading...
          </div>
        )}
      </div>
    </div>
  );
}

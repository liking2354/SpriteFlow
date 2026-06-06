import { useState, useRef, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { AssetItem } from "@/api/types";
import { Button } from "@/components/ui/Button";

interface Props {
  asset: AssetItem;
  onClose: () => void;
  onDelete?: (id: string) => void;
  onEdit?: (id: string) => void;
  onDownload?: (asset: AssetItem) => void;
}

/** 从 provenance 中解析 atlas 帧坐标 */
interface AtlasFrame {
  filename: string;
  frame: { x: number; y: number; w: number; h: number };
}

function parseAtlasFrames(provenance: Record<string, unknown> | null | undefined): AtlasFrame[] | null {
  if (!provenance) return null;
  const frames = provenance.frames;
  if (Array.isArray(frames) && frames.length > 0) return frames as AtlasFrame[];
  return null;
}

/** Spritesheet 帧序列播放器 */
function SpritesheetPlayer({ src, frames, onClose }: {
  src: string;
  frames: AtlasFrame[];
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [playing, setPlaying] = useState(true);
  const [fps, setFps] = useState(8);
  const [currentFrame, setCurrentFrame] = useState(0);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const animRef = useRef<number>(0);
  const lastTimeRef = useRef<number>(0);
  const frameIndexRef = useRef(0);

  // 加载 spritesheet 图片
  useEffect(() => {
    const img = new Image();
    img.src = src;
    img.onload = () => {
      imgRef.current = img;
      drawFrame(0);
    };
    return () => { imgRef.current = null; };
  }, [src]);

  const drawFrame = useCallback((index: number) => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || frames.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const frame = frames[index % frames.length];
    const { x, y, w, h } = frame.frame;
    const scale = 2; // 2x 放大显示

    canvas.width = w * scale;
    canvas.height = h * scale;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, x, y, w, h, 0, 0, canvas.width, canvas.height);
  }, [frames]);

  // 动画循环
  useEffect(() => {
    if (!playing) return;

    const animate = (time: number) => {
      if (!lastTimeRef.current) lastTimeRef.current = time;
      const elapsed = time - lastTimeRef.current;
      const interval = 1000 / fps;

      if (elapsed >= interval) {
        frameIndexRef.current = (frameIndexRef.current + 1) % frames.length;
        setCurrentFrame(frameIndexRef.current);
        drawFrame(frameIndexRef.current);
        lastTimeRef.current = time;
      }
      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animRef.current);
  }, [playing, fps, frames.length, drawFrame]);

  const togglePlay = useCallback(() => {
    setPlaying((p) => !p);
    lastTimeRef.current = 0;
  }, []);

  return (
    <div className="flex flex-col items-center gap-3">
      <canvas
        ref={canvasRef}
        className="max-w-full max-h-full pixelated rounded-lg"
        style={{ maxHeight: "calc(100vh - 200px)", imageRendering: "pixelated" }}
      />
      <div className="flex items-center gap-3 text-[12px] text-txt-2">
        <Button size="xs" variant="ghost" onClick={togglePlay}>
          {playing ? "⏸" : "▶"}
        </Button>
        <span>FPS:</span>
        {[4, 8, 12, 16].map((f) => (
          <button
            key={f}
            onClick={() => { setFps(f); lastTimeRef.current = 0; }}
            className={`px-1.5 py-0.5 rounded ${fps === f ? "bg-[var(--acc)] text-black" : "hover:bg-bg-2"}`}
          >
            {f}
          </button>
        ))}
        <span className="ml-2 font-mono text-txt-3">
          {currentFrame + 1}/{frames.length}
        </span>
      </div>
    </div>
  );
}

export function AssetPreviewModal({ asset, onClose, onDelete, onEdit, onDownload }: Props) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const isVideo = asset.type === "video";
  const isSpritesheet = asset.type === "spritesheet";
  const atlasFrames = parseAtlasFrames(asset.provenance);
  const isImage = asset.type === "image" || (!isVideo && !isSpritesheet);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.max(0.1, Math.min(5, z - e.deltaY * 0.001)));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (zoom <= 1) return;
    setDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    e.preventDefault();
  }, [zoom, pan]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }, [dragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setDragging(false);
  }, []);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  return (
    <div
      className="fixed inset-0 z-[9999] bg-black/85 flex flex-col"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-bg-1/90 backdrop-blur border-b border-line flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-mono text-txt-2">{asset.id}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded text-white"
            style={{ background: asset.source === "uploaded" ? "var(--cyan)" : asset.source === "generated" ? "var(--acc)" : "var(--violet)", color: "#001" }}>
            {asset.source}
          </span>
          {asset.width && asset.height && (
            <span className="text-[11px] text-txt-3">{asset.width}×{asset.height}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {(isImage || isSpritesheet) && (
            <>
              <Button size="xs" variant="ghost" onClick={() => setZoom((z) => Math.min(5, z + 0.25))}>＋</Button>
              <span className="text-[11px] text-txt-3 w-10 text-center">{Math.round(zoom * 100)}%</span>
              <Button size="xs" variant="ghost" onClick={() => setZoom((z) => Math.max(0.1, z - 0.25))}>−</Button>
              <Button size="xs" variant="ghost" onClick={resetView}>⊡</Button>
            </>
          )}
          {onEdit && (
            <Button size="xs" variant="outline" onClick={() => onEdit(asset.id)}>✎ {t("assets.preview.edit")}</Button>
          )}
          {onDownload && (
            <Button size="xs" variant="outline" onClick={() => onDownload(asset)}>⬇ {t("assets.preview.download")}</Button>
          )}
          {onDelete && (
            <Button size="xs" variant="ghost" className="text-red-400" onClick={() => onDelete(asset.id)}>🗑</Button>
          )}
          <Button size="xs" variant="ghost" onClick={onClose}>✕</Button>
        </div>
      </div>

      {/* Content */}
      <div
        ref={containerRef}
        className="flex-1 flex items-center justify-center overflow-hidden p-4"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ cursor: zoom > 1 ? (dragging ? "grabbing" : "grab") : "default" }}
      >
        {isVideo ? (
          <video
            src={asset.uri}
            controls
            autoPlay
            loop
            className="max-w-full max-h-full rounded-lg"
            style={{ maxHeight: "calc(100vh - 100px)" }}
          />
        ) : isSpritesheet && atlasFrames ? (
          <SpritesheetPlayer src={asset.uri} frames={atlasFrames} onClose={onClose} />
        ) : isImage ? (
          <img
            src={asset.uri}
            alt={asset.id}
            className="max-w-full max-h-full select-none pixelated"
            draggable={false}
            style={{
              transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
              transformOrigin: "center center",
            }}
          />
        ) : (
          <div className="text-txt-3">{t("assets.preview.noPreview")}</div>
        )}
      </div>

      {/* Bottom info */}
      <div className="flex items-center gap-3 px-4 py-2 bg-bg-1/90 backdrop-blur border-t border-line text-[10.5px] text-txt-3 flex-shrink-0">
        <span>{t("assets.preview.type")}: {asset.type}</span>
        <span>{t("assets.preview.hash")}: {asset.hash}</span>
        {asset.tags.length > 0 && (
          <span>{t("assets.preview.tags")}: {asset.tags.join(", ")}</span>
        )}
        {asset.group_id && <span className="text-[var(--acc)]">{t("assets.preview.group")}: {asset.group_id}</span>}
      </div>
    </div>
  );
}

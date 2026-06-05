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

export function AssetPreviewModal({ asset, onClose, onDelete, onEdit, onDownload }: Props) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const isVideo = asset.type === "video";
  const isImage = asset.type === "image" || !isVideo;

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
          {isImage && (
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

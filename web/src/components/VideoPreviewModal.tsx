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

/** 格式化秒数为 mm:ss 或 hh:mm:ss */
function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2];

export function VideoPreviewModal({ asset, onClose, onDelete, onEdit, onDownload }: Props) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  const [playing, setPlaying] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(asset.duration || 0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [seeking, setSeeking] = useState(false);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const [hoverX, setHoverX] = useState(0);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === " " || e.key === "k") {
        e.preventDefault();
        togglePlay();
      }
      if (e.key === "ArrowLeft") seekBy(-5);
      if (e.key === "ArrowRight") seekBy(5);
      if (e.key === "ArrowUp") { e.preventDefault(); setVolume(v => Math.min(1, v + 0.1)); }
      if (e.key === "ArrowDown") { e.preventDefault(); setVolume(v => Math.max(0, v - 0.1)); }
      if (e.key === "m") toggleMute();
      if (e.key === "f") toggleFullscreen();
      if (e.key === ",") seekFrame(-1);
      if (e.key === ".") seekFrame(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Sync video element state
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTime = () => setCurrentTime(v.currentTime);
    const onMeta = () => setDuration(v.duration || asset.duration || 0);
    const onEnd = () => setPlaying(false);

    v.addEventListener("timeupdate", onTime);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("ended", onEnd);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("ended", onEnd);
    };
  }, [asset.duration]);

  // Apply playback state
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (playing) v.play().catch(() => setPlaying(false));
    else v.pause();
  }, [playing]);

  // Apply volume
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.volume = volume;
    v.muted = muted;
  }, [volume, muted]);

  // Apply speed
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = speed;
  }, [speed]);

  // Fullscreen change
  useEffect(() => {
    const onFS = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFS);
    return () => document.removeEventListener("fullscreenchange", onFS);
  }, []);

  const togglePlay = () => setPlaying(p => !p);
  const toggleMute = () => setMuted(m => !m);
  const seekBy = (sec: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = Math.max(0, Math.min(v.duration || 0, v.currentTime + sec));
  };
  const seekFrame = (dir: number) => {
    // 假设 30fps: 1/30 ≈ 0.033s per frame; safe fallback 0.04
    const fps = 30;
    const frameDuration = 1 / fps;
    const v = videoRef.current;
    if (v) v.currentTime = Math.max(0, Math.min(v.duration || 0, v.currentTime + dir * frameDuration));
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (fullscreen) {
      document.exitFullscreen().catch(() => {});
    } else {
      containerRef.current.requestFullscreen().catch(() => {});
    }
  };

  // Progress bar handling
  const progressRatio = duration > 0 ? currentTime / duration : 0;

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const v = videoRef.current;
    if (v && duration > 0) v.currentTime = ratio * duration;
  };

  const handleProgressHover = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setHoverTime(duration * ratio);
    setHoverX(e.clientX - rect.left);
  };

  const cycleSpeed = () => {
    const idx = SPEEDS.indexOf(speed);
    setSpeed(SPEEDS[(idx + 1) % SPEEDS.length]);
  };

  const actualDuration = duration || asset.duration || 0;

  return (
    <div
      className="fixed inset-0 z-[9999] bg-black/90 flex flex-col"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/80 backdrop-blur border-b border-white/10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-mono text-white/60">{asset.id}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded text-white"
            style={{ background: "var(--violet)", color: "#001" }}>
            视频
          </span>
          {asset.width && asset.height && (
            <span className="text-[11px] text-white/40">{asset.width}×{asset.height}</span>
          )}
          {actualDuration > 0 && (
            <span className="text-[11px] text-white/40">{formatTime(actualDuration)}</span>
          )}
          <span className="text-[10px] text-white/30 font-mono">{asset.mime_type || "video/mp4"}</span>
        </div>
        <div className="flex items-center gap-2">
          {onEdit && (
            <Button size="xs" variant="outline" onClick={() => onEdit(asset.id)}>✎ 编辑</Button>
          )}
          {onDownload && (
            <Button size="xs" variant="outline" onClick={() => onDownload(asset)}>⬇ 下载</Button>
          )}
          {onDelete && (
            <Button size="xs" variant="ghost" className="text-red-400" onClick={() => onDelete(asset.id)}>🗑</Button>
          )}
          <Button size="xs" variant="ghost" onClick={onClose}>✕</Button>
        </div>
      </div>

      {/* Video area */}
      <div
        ref={containerRef}
        className="flex-1 flex items-center justify-center min-h-0 p-4"
      >
        <video
          ref={videoRef}
          src={asset.uri}
          autoPlay
          className="max-w-full max-h-full rounded-lg shadow-2xl"
          style={{ maxHeight: "calc(100vh - 180px)" }}
          onClick={togglePlay}
        />
      </div>

      {/* Controls bar */}
      <div className="flex-shrink-0 bg-black/80 backdrop-blur border-t border-white/10 px-4 pb-3 pt-2">
        {/* Progress bar */}
        <div
          ref={progressRef}
          className="relative w-full h-6 mb-2 cursor-pointer group flex items-center"
          onMouseDown={(e) => { handleProgressClick(e); }}
          onMouseMove={handleProgressHover}
          onMouseLeave={() => setHoverTime(null)}
        >
          {/* Track */}
          <div className="absolute left-0 right-0 h-1 rounded bg-white/20 group-hover:h-2 transition-all">
            {/* Buffered */}
            <div className="absolute left-0 top-0 h-full rounded bg-white/10" />
            {/* Played */}
            <div
              className="absolute left-0 top-0 h-full rounded bg-[var(--violet)]"
              style={{ width: `${progressRatio * 100}%` }}
            />
            {/* Hover preview */}
            {hoverTime !== null && (
              <>
                <div
                  className="absolute top-0 h-full w-0.5 bg-white/60"
                  style={{ left: hoverX }}
                />
                <div
                  className="absolute -top-7 -translate-x-1/2 px-1.5 py-0.5 rounded bg-black/80 text-white text-[10px] font-mono"
                  style={{ left: hoverX }}
                >
                  {formatTime(hoverTime)}
                </div>
              </>
            )}
          </div>
          {/* Thumb */}
          <div
            className="absolute w-3 h-3 rounded-full bg-white shadow -translate-x-1/2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ left: `${progressRatio * 100}%` }}
          />
        </div>

        {/* Controls row */}
        <div className="flex items-center gap-3">
          {/* Play / Pause */}
          <button onClick={togglePlay} className="text-white/80 hover:text-white text-lg w-7 h-7 flex items-center justify-center">
            {playing ? "⏸" : "▶"}
          </button>

          {/* Rewind / Forward */}
          <button onClick={() => seekBy(-10)} className="text-white/50 hover:text-white text-xs w-6 h-6 flex items-center justify-center" title="-10s">
            ⏪
          </button>
          <button onClick={() => seekBy(10)} className="text-white/50 hover:text-white text-xs w-6 h-6 flex items-center justify-center" title="+10s">
            ⏩
          </button>

          {/* Time */}
          <span className="text-[11px] font-mono text-white/60 tabular-nums min-w-[90px]">
            {formatTime(currentTime)} / {formatTime(actualDuration)}
          </span>

          {/* Volume */}
          <div className="flex items-center gap-1">
            <button onClick={toggleMute} className="text-white/60 hover:text-white text-sm w-5 h-5 flex items-center justify-center">
              {muted || volume === 0 ? "🔇" : volume < 0.5 ? "🔉" : "🔊"}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={muted ? 0 : volume}
              onChange={(e) => { setVolume(Number(e.target.value)); setMuted(false); }}
              className="w-20 h-1 accent-[var(--violet)] cursor-pointer"
            />
          </div>

          {/* Frame step */}
          <button onClick={() => seekFrame(-1)} className="text-white/40 hover:text-white text-[10px] w-6 h-6 flex items-center justify-center" title="上一帧 (, )">
            ◀
          </button>
          <button onClick={() => seekFrame(1)} className="text-white/40 hover:text-white text-[10px] w-6 h-6 flex items-center justify-center" title="下一帧 (.)">
            ▶
          </button>

          <div className="flex-1" />

          {/* Speed */}
          <button
            onClick={cycleSpeed}
            className="text-[11px] font-mono text-white/60 hover:text-white px-1.5 py-0.5 rounded hover:bg-white/10"
          >
            {speed}x
          </button>

          {/* Fullscreen */}
          <button onClick={toggleFullscreen} className="text-white/60 hover:text-white text-sm w-6 h-6 flex items-center justify-center" title="全屏 (F)">
            {fullscreen ? "⤓" : "⛶"}
          </button>
        </div>
      </div>

      {/* Bottom info */}
      <div className="flex items-center gap-3 px-4 py-2 bg-black/80 border-t border-white/10 text-[10.5px] text-white/30 flex-shrink-0">
        <span>类型: {asset.type}</span>
        <span>哈希: {asset.hash}</span>
        {asset.tags.length > 0 && (
          <span>标签: {asset.tags.join(", ")}</span>
        )}
        {asset.group_id && <span className="text-[var(--violet)]">分组: {asset.group_id}</span>}
      </div>
    </div>
  );
}

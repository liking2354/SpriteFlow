import { useEffect, useRef, useState } from "react";

interface FrameItem {
  /** base64 data URL 或 HTTP URL */
  dataUrl: string;
  /** 帧时间戳（秒） */
  timestamp?: number;
  /** 帧尺寸 */
  width?: number;
  height?: number;
}

interface Props {
  frames: FrameItem[];
  fps?: number;
  /** 初始播放速度倍率 */
  initialSpeed?: number;
  /** 默认循环播放 */
  defaultLoop?: boolean;
}

export function FrameAnimationPreview({
  frames,
  fps = 8,
  initialSpeed = 1,
  defaultLoop = true,
}: Props) {
  const [playing, setPlaying] = useState(false);
  const [loop, setLoop] = useState(defaultLoop);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [speedScale, setSpeedScale] = useState(initialSpeed);
  const intervalRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const safeIdx = frames.length > 0 ? currentIdx % frames.length : 0;
  const currentFrame = frames[safeIdx];

  // 基础速度：fps ≤ 12 按实际 fps，否则按 12fps 基准
  const baseMs = fps <= 12 ? 1000 / fps : 1000 / 12;
  const speedMs = Math.max(50, baseMs / speedScale);

  // 播放定时器
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const id = setInterval(() => {
      setCurrentIdx((i) => {
        const next = i + 1;
        if (next >= frames.length) {
          if (!loop) setPlaying(false);
          return loop ? 0 : i;
        }
        return next;
      });
    }, speedMs);
    intervalRef.current = id;
    return () => clearInterval(id);
  }, [playing, frames.length, loop, speedMs]);

  // frames 变化时重置索引
  useEffect(() => {
    setCurrentIdx((i) => Math.min(i, Math.max(0, frames.length - 1)));
  }, [frames.length]);

  if (frames.length === 0) return null;

  return (
    <div style={{ marginTop: 8 }}>
      {/* 主预览区 */}
      <div
        style={{
          background: "var(--bg-0)",
          borderRadius: 6,
          border: "1px solid var(--line)",
          overflow: "hidden",
          textAlign: "center",
          padding: 8,
        }}
      >
        <div
          style={{
            maxWidth: "100%",
            maxHeight: 240,
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#0d0d1a",
            borderRadius: 4,
            overflow: "hidden",
            minHeight: 120,
          }}
        >
          {currentFrame && (
            <img
              src={currentFrame.dataUrl}
              alt={`Frame ${safeIdx + 1}`}
              style={{
                maxWidth: "100%",
                maxHeight: 240,
                width: "auto",
                height: "auto",
                objectFit: "contain",
                imageRendering: "pixelated",
                display: "block",
              }}
            />
          )}
        </div>

        {/* 帧指示器 */}
        <div
          style={{
            fontSize: 10,
            color: "var(--txt-3)",
            marginTop: 6,
            fontFamily: "monospace",
          }}
        >
          帧 {safeIdx + 1} / {frames.length}
          {currentFrame?.timestamp != null &&
            `  ·  ${currentFrame.timestamp.toFixed(2)}s`}
        </div>

        {/* 进度条 */}
        <input
          type="range"
          min={0}
          max={Math.max(0, frames.length - 1)}
          value={currentIdx}
          onChange={(e) => {
            setCurrentIdx(parseInt(e.target.value, 10));
            setPlaying(false);
          }}
          style={{
            width: "100%",
            height: 4,
            marginTop: 6,
            cursor: "pointer",
            accentColor: "var(--acc)",
          }}
        />

        {/* 控制按钮 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
            marginTop: 6,
            flexWrap: "wrap",
          }}
        >
          <Btn title="首帧" onClick={() => { setCurrentIdx(0); setPlaying(false); }}>
            ⏮
          </Btn>
          <Btn
            title="上一帧"
            onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
          >
            ◀
          </Btn>
          <Btn
            title={playing ? "暂停" : "播放"}
            onClick={() => setPlaying((v) => !v)}
            accent
          >
            {playing ? "⏸" : "▶"}
          </Btn>
          <Btn
            title="下一帧"
            onClick={() =>
              setCurrentIdx((i) => Math.min(frames.length - 1, i + 1))
            }
          >
            ▶
          </Btn>
          <Btn
            title="末帧"
            onClick={() => { setCurrentIdx(frames.length - 1); setPlaying(false); }}
          >
            ⏭
          </Btn>

          {/* 分隔 */}
          <span style={{ width: 1, height: 14, background: "var(--line)", margin: "0 4px" }} />

          <button
            type="button"
            onClick={() => setLoop((v) => !v)}
            style={{
              fontSize: 10,
              padding: "2px 6px",
              borderRadius: 3,
              border: `1px solid ${loop ? "var(--acc)" : "var(--line)"}`,
              background: loop ? "rgba(99,102,241,0.12)" : "transparent",
              color: loop ? "var(--acc)" : "var(--txt-3)",
              cursor: "pointer",
            }}
          >
            🔁 {loop ? "开" : "关"}
          </button>
        </div>

        {/* 速度控制 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            marginTop: 4,
            fontSize: 10,
            color: "var(--txt-3)",
          }}
        >
          <span>速度</span>
          <input
            type="range"
            min={0.25}
            max={4}
            step={0.25}
            value={speedScale}
            onChange={(e) => setSpeedScale(parseFloat(e.target.value))}
            style={{
              width: 80,
              height: 3,
              cursor: "pointer",
              accentColor: "var(--acc)",
            }}
          />
          <span style={{ fontFamily: "monospace", minWidth: 32, textAlign: "right" }}>
            {speedScale}×
          </span>
        </div>
      </div>
    </div>
  );
}

function Btn({
  onClick,
  children,
  title,
  accent,
}: {
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
  accent?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      style={{
        fontSize: 11,
        width: 26,
        height: 22,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 4,
        border: `1px solid ${accent ? "var(--acc)" : "var(--line)"}`,
        background: accent ? "rgba(99,102,241,0.12)" : "transparent",
        color: accent ? "var(--acc)" : "var(--txt-2)",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

export default FrameAnimationPreview;

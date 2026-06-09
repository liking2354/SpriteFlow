interface FrameItem {
  dataUrl: string;
  timestamp?: number;
  width?: number;
  height?: number;
}

interface Props {
  frames: FrameItem[];
  selected: boolean[];
  onSelectionChange: (index: number, checked: boolean) => void;
  /** 标记相似/重复帧 */
  duplicateMarkers?: Map<number, { groupId: number; totalInGroup: number }>;
}

export function FrameThumbnails({
  frames,
  selected,
  onSelectionChange,
  duplicateMarkers,
}: Props) {
  if (frames.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 6,
        padding: "4px 0",
      }}
    >
      {frames.map((f, i) => {
        const dup = duplicateMarkers?.get(i);
        const sel = selected[i] ?? true;
        return (
          <div
            key={i}
            style={{
              width: 80,
              textAlign: "center",
              border: dup
                ? "2px solid #ef4444"
                : sel
                  ? "1px solid var(--acc)"
                  : "1px solid var(--line)",
              borderRadius: 6,
              overflow: "hidden",
              position: "relative",
              cursor: "pointer",
              background: "var(--bg-0)",
              transition: "border-color 0.15s",
            }}
            onClick={() => onSelectionChange(i, !sel)}
          >
            {/* 选择标记 */}
            <div
              style={{
                position: "absolute",
                top: 2,
                right: 2,
                zIndex: 1,
                width: 16,
                height: 16,
                borderRadius: 3,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: `1px solid ${sel ? "var(--acc)" : "var(--line)"}`,
                background: sel
                  ? "var(--acc)"
                  : "rgba(0,0,0,0.5)",
                fontSize: 8,
                color: "#fff",
              }}
            >
              {sel ? "✓" : ""}
            </div>

            {/* 重复标记 */}
            {dup && (
              <div
                style={{
                  position: "absolute",
                  top: 2,
                  left: 2,
                  zIndex: 1,
                  background: "#ef4444",
                  color: "#fff",
                  fontSize: 9,
                  padding: "1px 4px",
                  borderRadius: 3,
                  fontWeight: 600,
                }}
              >
                ×{dup.totalInGroup}
              </div>
            )}

            <img
              src={f.dataUrl}
              alt={`帧 ${i + 1}`}
              loading="lazy"
              style={{
                width: "100%",
                height: 52,
                objectFit: "contain",
                display: "block",
                background: "#0d0d1a",
                imageRendering: "pixelated",
              }}
            />
            <div
              style={{
                background: sel
                  ? "rgba(99,102,241,0.15)"
                  : "rgba(0,0,0,0.3)",
                color: "var(--txt-2)",
                fontSize: 10,
                padding: "2px 0",
                fontFamily: "monospace",
              }}
            >
              #{i + 1}
              {f.timestamp != null && (
                <span style={{ fontSize: 8, opacity: 0.5, marginLeft: 2 }}>
                  {f.timestamp.toFixed(1)}s
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default FrameThumbnails;

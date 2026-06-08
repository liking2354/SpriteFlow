import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Popover } from "./Popover";

/* 尺寸选择：分辨率（2K/4K） + 比例（智能/1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9） + 自定义 W/H 联动 */

interface Props {
  resolution: "2k" | "4k";
  ratio: string;                      // "smart" | "1:1" | ...
  width: number;
  height: number;
  onChange: (next: {
    resolution: "2k" | "4k";
    ratio: string;
    width: number;
    height: number;
  }) => void;
}

export const RATIOS: Array<{ key: string; label: string; w: number; h: number; icon: string }> = [
  { key: "smart", label: "智能", w: 0, h: 0, icon: "smart" },
  { key: "1:1", label: "1:1", w: 1, h: 1, icon: "□" },
  { key: "3:4", label: "3:4", w: 3, h: 4, icon: "▯" },
  { key: "4:3", label: "4:3", w: 4, h: 3, icon: "▭" },
  { key: "16:9", label: "16:9", w: 16, h: 9, icon: "▭" },
  { key: "9:16", label: "9:16", w: 9, h: 16, icon: "▯" },
  { key: "2:3", label: "2:3", w: 2, h: 3, icon: "▯" },
  { key: "3:2", label: "3:2", w: 3, h: 2, icon: "▭" },
  { key: "21:9", label: "21:9", w: 21, h: 9, icon: "▭" },
];

/** 根据分辨率 + 比例计算 W/H（≥3686400 像素） */
function calcSize(resolution: "2k" | "4k", ratio: string): { w: number; h: number } {
  const target = resolution === "4k" ? 4096 * 4096 : 2048 * 2048;
  const r = RATIOS.find((x) => x.key === ratio);
  if (!r || r.key === "smart") {
    const side = Math.round(Math.sqrt(target));
    return { w: side, h: side };
  }
  // wpart : hpart -> w = k*wpart, h = k*hpart, w*h = target
  const k = Math.sqrt(target / (r.w * r.h));
  return {
    w: Math.round(k * r.w),
    h: Math.round(k * r.h),
  };
}

export function SizePopover(props: Props) {
  const { t } = useTranslation();
  const { resolution, ratio, width, height, onChange } = props;

  const [w, setW] = useState(width);
  const [h, setH] = useState(height);
  const [linked, setLinked] = useState(true);

  useEffect(() => {
    setW(width);
    setH(height);
  }, [width, height]);

  const setRes = (next: "2k" | "4k") => {
    const s = calcSize(next, ratio);
    onChange({ resolution: next, ratio, width: s.w, height: s.h });
  };
  const setRatio = (r: string) => {
    const s = calcSize(resolution, r);
    onChange({ resolution, ratio: r, width: s.w, height: s.h });
  };

  const commit = (nw: number, nh: number) => {
    onChange({ resolution, ratio: "custom", width: nw, height: nh });
  };

  const triggerLabel = `${resolution} · ${ratio === "custom" ? `${width}×${height}` : ratio}`;

  return (
    <Popover
      width={468}
      placement="bottom-start"
      trigger={
        <button
          type="button"
          className="flex items-center gap-1.5 h-8 px-3 rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:border-[#2f3647] hover:text-txt-0 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="4" y="4" width="16" height="16" rx="2" />
          </svg>
          <span className="font-mono">{triggerLabel}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
      }
    >
      <div className="p-4">
        {/* 分辨率 */}
        <div className="text-[11px] text-txt-3 uppercase tracking-[1px] mb-2">
          {t("size.resolution")}
        </div>
        <div className="flex bg-bg-0 border border-line rounded-s p-[3px] gap-[3px] mb-4">
          {(["2k", "4k"] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRes(r)}
              className={`flex-1 h-8 rounded-[6px] text-[12px] font-medium transition-colors ${
                resolution === r ? "text-[var(--acc)]" : "text-txt-2 hover:text-txt-0"
              }`}
              style={resolution === r ? { background: "var(--acc-soft)" } : undefined}
            >
              {r}
            </button>
          ))}
        </div>

        {/* 比例：图形居中 + 文字底部，统一高度 */}
        <div className="text-[11px] text-txt-3 uppercase tracking-[1px] mb-2">
          {t("size.ratio")}
        </div>
        <div className="grid grid-cols-9 gap-1.5 mb-4">
          {RATIOS.map((r) => {
            const active = ratio === r.key;
            // 在 22×22 框内按比例缩放图形
            const box = 20;
            let bw = box;
            let bh = box;
            if (r.w && r.h) {
              if (r.w >= r.h) {
                bw = box;
                bh = Math.max(6, Math.round((r.h / r.w) * box));
              } else {
                bh = box;
                bw = Math.max(6, Math.round((r.w / r.h) * box));
              }
            }
            return (
              <button
                key={r.key}
                type="button"
                onClick={() => setRatio(r.key)}
                className={`flex flex-col items-center justify-between h-[58px] py-2 rounded-s border transition-colors ${
                  active
                    ? "border-[var(--acc)] text-[var(--acc)]"
                    : "border-line text-txt-2 hover:border-[#2f3647] hover:text-txt-1"
                }`}
                style={active ? { background: "var(--acc-soft)" } : undefined}
              >
                <span className="flex-1 grid place-items-center w-full">
                  {r.key === "smart" ? (
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 3 4 9v6l8 6 8-6V9z" />
                    </svg>
                  ) : (
                    <span
                      className="block border-[1.5px] border-current rounded-[2px]"
                      style={{ width: `${bw}px`, height: `${bh}px` }}
                    />
                  )}
                </span>
                <span className="text-[9.5px] font-mono leading-none">{r.label}</span>
              </button>
            );
          })}
        </div>

        {/* 自定义 W/H */}
        <div className="text-[11px] text-txt-3 uppercase tracking-[1px] mb-2">
          {t("size.custom")}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0 flex items-center gap-2 px-2.5 h-9 bg-bg-0 border border-line rounded-s">
            <span className="text-[11px] text-txt-3 font-mono flex-shrink-0">W</span>
            <input
              type="number"
              value={w}
              onChange={(e) => {
                const nw = Number(e.target.value) || 0;
                setW(nw);
                if (linked && height && width) {
                  const rr = height / width;
                  const nh = Math.round(nw * rr);
                  setH(nh);
                  commit(nw, nh);
                } else {
                  commit(nw, h);
                }
              }}
              className="w-full min-w-0 bg-transparent text-[12px] text-txt-0 font-mono text-right outline-none"
            />
          </div>
          <button
            type="button"
            onClick={() => setLinked(!linked)}
            className={`h-9 w-8 flex-shrink-0 grid place-items-center rounded-s border text-[12px] ${
              linked
                ? "border-[var(--acc)] text-[var(--acc)]"
                : "border-line text-txt-3"
            }`}
            title="lock aspect ratio"
          >
            🔗
          </button>
          <div className="flex-1 min-w-0 flex items-center gap-2 px-2.5 h-9 bg-bg-0 border border-line rounded-s">
            <span className="text-[11px] text-txt-3 font-mono flex-shrink-0">H</span>
            <input
              type="number"
              value={h}
              onChange={(e) => {
                const nh = Number(e.target.value) || 0;
                setH(nh);
                if (linked && height && width) {
                  const rr = width / height;
                  const nw = Math.round(nh * rr);
                  setW(nw);
                  commit(nw, nh);
                } else {
                  commit(w, nh);
                }
              }}
              className="w-full min-w-0 bg-transparent text-[12px] text-txt-0 font-mono text-right outline-none"
            />
          </div>
        </div>
        <div className="mt-2 text-[10.5px] text-txt-3 font-mono">
          {w * h >= 3_686_400 ? (
            <span style={{ color: "var(--green)" }}>
              ✓ {(w * h).toLocaleString()} px
            </span>
          ) : (
            <span style={{ color: "var(--amber)" }}>
              ⚠ {(w * h).toLocaleString()} px &lt; 3,686,400
            </span>
          )}
        </div>
      </div>
    </Popover>
  );
}

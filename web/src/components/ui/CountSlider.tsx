import { useTranslation } from "react-i18next";
import { Popover } from "./Popover";

interface Props {
  value: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}

export function CountSlider({ value, min = 1, max = 15, onChange }: Props) {
  const { t } = useTranslation();
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <Popover
      width={300}
      placement="bottom-start"
      trigger={
        <button
          type="button"
          className="flex items-center gap-1.5 h-8 px-3 rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:border-[#2f3647] hover:text-txt-0 transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          <span className="font-mono">{t("size.maxN", { n: value })}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
      }
    >
      <div className="p-4">
        <div className="text-[11px] text-txt-3 uppercase tracking-[1px] mb-3">
          {t("size.maxImagesLabel")}
        </div>
        <div className="flex items-center gap-3">
          <div className="relative flex-1 h-1 bg-bg-3 rounded-full">
            <div
              className="absolute top-0 left-0 h-1 rounded-full"
              style={{
                width: `${pct}%`,
                background: "linear-gradient(90deg, var(--acc), var(--cyan))",
              }}
            />
            <input
              type="range"
              min={min}
              max={max}
              value={value}
              onChange={(e) => onChange(Number(e.target.value))}
              className="absolute inset-0 w-full opacity-0 cursor-pointer"
              style={{ height: 16, top: -7 }}
            />
            <div
              className="absolute -top-1.5 w-4 h-4 rounded-full bg-white shadow-md pointer-events-none"
              style={{ left: `calc(${pct}% - 8px)` }}
            />
          </div>
          <input
            type="number"
            min={min}
            max={max}
            value={value}
            onChange={(e) => {
              const v = Math.max(min, Math.min(max, Number(e.target.value) || min));
              onChange(v);
            }}
            className="w-16 h-8 px-2 bg-bg-0 border border-line rounded-s text-[12px] text-txt-0 font-mono text-center outline-none focus:border-[var(--acc)]"
          />
        </div>
      </div>
    </Popover>
  );
}

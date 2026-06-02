import { useTranslation } from "react-i18next";
import { useThemeStore, type AccentColor, type ThemeMode } from "@/stores/theme";
import { setLanguage, supportedLngs, type SupportedLng } from "@/i18n";

const ACCENTS: AccentColor[] = ["blue", "violet", "cyan", "pink", "amber"];
const ACCENT_COLORS: Record<AccentColor, string> = {
  blue: "#5b8cff",
  violet: "#a571ff",
  cyan: "#3ee0d0",
  pink: "#ff6ba6",
  amber: "#ffb648",
};

export function ThemeSwitcher() {
  const { t, i18n } = useTranslation();
  const { theme, accent, setTheme, setAccent } = useThemeStore();

  return (
    <div className="flex items-center gap-2">
      {/* 强调色 */}
      <div className="flex items-center gap-1 px-2 h-7 bg-bg-3 border border-line rounded-full">
        {ACCENTS.map((c) => (
          <button
            key={c}
            onClick={() => setAccent(c)}
            title={t(`topbar.accent.${c}`)}
            className={`w-3.5 h-3.5 rounded-full transition-transform ${
              accent === c ? "scale-110 ring-2 ring-white/30" : "hover:scale-110"
            }`}
            style={{
              background: ACCENT_COLORS[c],
              boxShadow: accent === c ? `0 0 8px ${ACCENT_COLORS[c]}` : undefined,
            }}
            aria-label={c}
          />
        ))}
      </div>

      {/* 主题切换 */}
      <button
        onClick={() => setTheme(theme === "dark" ? ("light" as ThemeMode) : "dark")}
        className="flex items-center gap-1.5 px-3 h-7 bg-bg-3 border border-line rounded-full text-[11px] text-txt-1 hover:text-txt-0 hover:border-[#2f3647] transition-colors"
        title={t("topbar.theme")}
      >
        {theme === "dark" ? (
          <>
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
            {t("topbar.themeDark")}
          </>
        ) : (
          <>
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
            </svg>
            {t("topbar.themeLight")}
          </>
        )}
      </button>

      {/* 语言切换 */}
      <select
        value={i18n.language}
        onChange={(e) => setLanguage(e.target.value as SupportedLng)}
        className="h-7 px-2 bg-bg-3 border border-line rounded-full text-[11px] text-txt-1 hover:text-txt-0 hover:border-[#2f3647] transition-colors cursor-pointer font-mono"
      >
        {supportedLngs.map((l) => (
          <option key={l} value={l} className="bg-bg-1">
            {l === "zh-CN" ? "中文" : "English"}
          </option>
        ))}
      </select>
    </div>
  );
}

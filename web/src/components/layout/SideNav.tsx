import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

const ITEMS = [
  { to: "/", key: "generate", icon: "✨" },
  { to: "/video", key: "video", icon: "🎬" },
  { to: "/editor", key: "editor", icon: "✎" },
  { to: "/spritesheet", key: "spritesheet", icon: "▦" },
  { to: "/workflows", key: "workflows", icon: "⚙" },
  { to: "/assets", key: "assets", icon: "🖼" },
  { to: "/nodes", key: "nodes", icon: "◆" },
  { to: "/routing", key: "routing", icon: "↳" },
];

export function SideNav() {
  const { t } = useTranslation();
  return (
    <aside
      className="relative w-[200px] border-r border-line flex flex-col"
      style={{ background: "var(--bg-1)" }}
    >
      {/* 右边 1px 渐变光线 */}
      <div
        className="absolute top-0 right-0 bottom-0 w-px pointer-events-none"
        style={{
          background:
            "linear-gradient(180deg, transparent, rgba(var(--acc-rgb), 0.25) 30%, rgba(var(--acc-rgb), 0.25) 70%, transparent)",
          opacity: 0.5,
        }}
      />

      <div className="px-5 pt-5 pb-3 text-[10.5px] uppercase tracking-[1.5px] text-txt-2 font-semibold flex items-center gap-2">
        <span
          className="w-1 h-1 rounded-full"
          style={{
            background: "var(--acc)",
            boxShadow: "0 0 6px var(--acc)",
          }}
        />
        {t("common.appName")}
      </div>

      <nav className="px-3 flex flex-col gap-1">
        {ITEMS.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.to === "/"}
            className={({ isActive }) =>
              `relative flex items-center gap-2.5 px-3 h-9 rounded-s text-[12.5px] transition-all ${
                isActive
                  ? "text-txt-0"
                  : "text-txt-1 hover:bg-bg-3 hover:text-txt-0"
              }`
            }
            style={({ isActive }) =>
              isActive
                ? {
                    background: "var(--acc-soft)",
                    color: "var(--acc)",
                    fontWeight: 600,
                    boxShadow:
                      "inset 2px 0 0 var(--acc), 0 0 16px rgba(var(--acc-rgb), 0.15)",
                  }
                : undefined
            }
          >
            <span className="w-5 text-center text-[14px]">{it.icon}</span>
            <span>{t(`nav.${it.key}`)}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto px-5 py-4 border-t border-[var(--line-soft)] text-[10px] text-txt-3 font-mono leading-relaxed">
        <div className="flex items-center gap-1.5 mb-1">
          <span
            className="w-1 h-1 rounded-full"
            style={{
              background: "var(--green)",
              boxShadow: "0 0 5px var(--green)",
            }}
          />
          <span>POWERED BY</span>
        </div>
        <div className="text-txt-2">Seedream 5.0 Lite</div>
      </div>
    </aside>
  );
}

import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

const ITEMS = [
  { to: "/", key: "generate", icon: "✨" },
  { to: "/workflows", key: "workflows", icon: "⚙" },
  { to: "/assets", key: "assets", icon: "🖼" },
  { to: "/nodes", key: "nodes", icon: "◆" },
  { to: "/routing", key: "routing", icon: "↳" },
];

export function SideNav() {
  const { t } = useTranslation();
  return (
    <aside className="w-[200px] bg-bg-1 border-r border-line flex flex-col">
      <div className="px-5 pt-5 pb-3 text-[10.5px] uppercase tracking-[1.2px] text-txt-2 font-semibold">
        {t("common.appName")}
      </div>

      <nav className="px-3 flex flex-col gap-1">
        {ITEMS.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            end={it.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 h-9 rounded-s text-[12.5px] transition-colors ${
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
                  }
                : undefined
            }
          >
            <span className="w-5 text-center text-[14px]">{it.icon}</span>
            <span>{t(`nav.${it.key}`)}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto px-5 py-4 border-t border-[var(--line-soft)] text-[10px] text-txt-3 font-mono">
        Powered by Seedream 5.0 Lite
      </div>
    </aside>
  );
}

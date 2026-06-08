import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMenuStore } from "@/stores/menu";
import { navIcons } from "./NavIcons";
import { MenuSettings } from "./MenuSettings";

export function SideNav() {
  const { t } = useTranslation();
  const { items, collapsed, toggleCollapsed, setSettingsOpen } = useMenuStore();

  const sections = [
    { key: "generate", label: t("menu.sectionGenerate", "生成工具") },
    { key: "manage", label: t("menu.sectionManage", "资源管理") },
  ] as const;

  const grouped = (section: string) =>
    items
      .filter((it) => it.section === section && it.visible)
      .sort((a, b) => a.order - b.order);

  const asideWidth = collapsed ? 56 : 200;

  return (
    <>
      <aside
        className="relative border-r border-[var(--line)] flex flex-col transition-all duration-200"
        style={{ background: "var(--bg-1)", width: asideWidth, minWidth: asideWidth }}
      >
        {/* 右边 1px 渐变光线 */}
        <div
          className="absolute top-0 right-0 bottom-0 w-px pointer-events-none"
          style={{
            background: `linear-gradient(180deg, transparent, rgba(var(--acc-rgb), 0.25) 30%, rgba(var(--acc-rgb), 0.25) 70%, transparent)`,
            opacity: 0.5,
          }}
        />

        {/* 折叠时：Logo 图标 */}
        {collapsed ? (
          <div className="flex items-center justify-center pt-5 pb-3">
            <div
              className="w-8 h-8 rounded flex items-center justify-center text-sm font-bold"
              style={{
                background: "var(--acc-soft)",
                color: "var(--acc)",
              }}
            >
              S
            </div>
          </div>
        ) : (
          <div className="px-5 pt-5 pb-3">
            <div
              className="text-[10.5px] uppercase tracking-[1.5px] text-[var(--txt-2)] font-semibold flex items-center gap-2"
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{
                  background: "var(--acc)",
                  boxShadow: "0 0 6px var(--acc)",
                }}
              />
              {t("common.appName")}
            </div>
          </div>
        )}

        {/* 导航菜单 */}
        <nav className="flex-1 px-2 py-1 space-y-4 overflow-y-auto">
          {sections.map((sec) => {
            const secItems = grouped(sec.key);
            if (secItems.length === 0) return null;
            return (
              <div key={sec.key}>
                {!collapsed && (
                  <div
                    className="px-3 pb-1 text-[9.5px] uppercase tracking-[1.2px] font-semibold"
                    style={{ color: "var(--txt-3)" }}
                  >
                    {sec.label}
                  </div>
                )}
                <div className="space-y-0.5">
                  {secItems.map((it) => (
                    <NavLink
                      key={it.id}
                      to={it.to}
                      end={it.to === "/"}
                      className={({ isActive }) =>
                        `relative flex items-center rounded-s transition-all duration-150 ${
                          collapsed
                            ? "justify-center h-9 w-10 mx-auto"
                            : "gap-2.5 px-3 h-9"
                        } ${
                          isActive
                            ? "text-[var(--txt-0)]"
                            : "text-[var(--txt-1)] hover:bg-[var(--bg-3)] hover:text-[var(--txt-0)]"
                        }`
                      }
                      style={({ isActive }) =>
                        isActive
                          ? {
                              background: "var(--acc-soft)",
                              color: "var(--acc)",
                              fontWeight: 600,
                              boxShadow: `inset 2px 0 0 var(--acc), 0 0 16px rgba(var(--acc-rgb), 0.15)`,
                            }
                          : undefined
                      }
                      title={collapsed ? t(it.i18nKey) : undefined}
                    >
                      <span
                        className={`flex items-center justify-center ${
                          collapsed ? "w-5 h-5" : "w-5"
                        } text-[15px]`}
                      >
                        {navIcons[it.id] ?? "◆"}
                      </span>
                      {!collapsed && (
                        <span className="text-[12.5px] truncate">
                          {t(it.i18nKey)}
                        </span>
                      )}

                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* 底部操作区 */}
        <div
          className="mt-auto border-t flex items-center gap-1 px-2 py-2"
          style={{ borderColor: "var(--line-soft)" }}
        >
          {/* 折叠/展开按钮 */}
          <button
            onClick={toggleCollapsed}
            className="flex-1 h-8 flex items-center justify-center rounded text-xs transition-all hover:bg-white/5"
            style={{ color: "var(--txt-2)" }}
            title={collapsed ? t("menu.expand", "展开") : t("menu.collapse", "折叠")}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{
                transform: collapsed ? "rotate(180deg)" : "none",
                transition: "transform 0.2s",
              }}
            >
              <path d="M15 18l-6-6 6-6" />
            </svg>
            {!collapsed && (
              <span className="ml-1.5 text-[10px]">
                {t("menu.collapse", "折叠")}
              </span>
            )}
          </button>

          {/* 菜单设置按钮 */}
          {!collapsed && (
            <button
              onClick={() => setSettingsOpen(true)}
              className="w-8 h-8 flex items-center justify-center rounded text-sm transition-all hover:bg-white/5"
              style={{ color: "var(--txt-2)" }}
              title={t("menu.settings", "菜单管理")}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
              </svg>
            </button>
          )}
        </div>

        {/* 折叠时的底部图标 */}
        {collapsed && (
          <div className="pb-3 flex justify-center">
            <button
              onClick={() => setSettingsOpen(true)}
              className="w-8 h-8 flex items-center justify-center rounded text-sm transition-all hover:bg-white/5"
              style={{ color: "var(--txt-2)" }}
              title={t("menu.settings", "菜单管理")}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
              </svg>
            </button>
          </div>
        )}

        {/* 底部品牌信息（仅展开时） */}
        {!collapsed && (
          <div
            className="px-5 py-3 text-[10px] font-mono leading-relaxed"
            style={{
              color: "var(--txt-3)",
              borderTop: "1px solid var(--line-soft)",
            }}
          >
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
            <div style={{ color: "var(--txt-2)" }}>Seedream 5.0 Lite</div>
          </div>
        )}
      </aside>

      {/* 菜单管理面板 */}
      <MenuSettings />
    </>
  );
}

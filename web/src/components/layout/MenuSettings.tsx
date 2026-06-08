import { useTranslation } from "react-i18next";
import { useMenuStore, type MenuItem } from "@/stores/menu";

export function MenuSettings() {
  const { t } = useTranslation();
  const { items, collapsed, settingsOpen, setSettingsOpen, toggleItem, moveItem, resetDefaults } =
    useMenuStore();

  if (!settingsOpen) return null;

  const sections = [
    { key: "generate", label: t("menu.sectionGenerate", "生成工具") },
    { key: "manage", label: t("menu.sectionManage", "资源管理") },
  ] as const;

  const grouped = (section: string) =>
    items.filter((it) => it.section === section).sort((a, b) => a.order - b.order);

  const sidebarWidth = collapsed ? 56 : 200;

  return (
    <>
      {/* 遮罩 */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={() => setSettingsOpen(false)}
      />
      {/* 面板 */}
      <div
        className="fixed top-0 h-screen w-72 z-50 border-l border-[var(--line)] flex flex-col shadow-2xl animate-slide-in"
        style={{ background: "var(--bg-1)", left: `${sidebarWidth}px` }}
      >
        {/* 头部 */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: "var(--line-soft)" }}
        >
          <span className="text-sm font-semibold" style={{ color: "var(--txt-0)" }}>
            {t("menu.settings", "菜单管理")}
          </span>
          <button
            onClick={() => setSettingsOpen(false)}
            className="w-7 h-7 flex items-center justify-center rounded text-xs hover:bg-white/5"
            style={{ color: "var(--txt-2)" }}
          >
            ✕
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
          {sections.map((sec) => (
            <div key={sec.key}>
              <div
                className="text-[10px] uppercase tracking-[1.5px] font-semibold mb-2 px-1"
                style={{ color: "var(--txt-3)" }}
              >
                {sec.label}
              </div>
              <div className="space-y-0.5">
                {grouped(sec.key).map((it, idx, arr) => (
                  <MenuItemRow
                    key={it.id}
                    item={it}
                    isFirst={idx === 0}
                    isLast={idx === arr.length - 1}
                    onToggle={() => toggleItem(it.id)}
                    onMoveUp={() => moveItem(it.id, "up")}
                    onMoveDown={() => moveItem(it.id, "down")}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* 底部 */}
        <div
          className="px-5 py-3 border-t"
          style={{ borderColor: "var(--line-soft)" }}
        >
          <button
            onClick={resetDefaults}
            className="w-full h-8 rounded text-[11px] font-medium transition-all hover:opacity-80"
            style={{
              background: "var(--bg-2)",
              color: "var(--txt-2)",
              border: "1px solid var(--line)",
            }}
          >
            {t("menu.resetDefaults", "恢复默认")}
          </button>
        </div>
      </div>
    </>
  );
}

function MenuItemRow({
  item,
  isFirst,
  isLast,
  onToggle,
  onMoveUp,
  onMoveDown,
}: {
  item: MenuItem;
  isFirst: boolean;
  isLast: boolean;
  onToggle: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="flex items-center gap-2 px-2 h-9 rounded text-[12px] transition-all"
      style={{
        background: item.visible ? "var(--bg-2)" : "transparent",
        color: item.visible ? "var(--txt-1)" : "var(--txt-3)",
      }}
    >
      {/* 可见性开关 */}
      <button
        onClick={onToggle}
        className="w-8 h-7 flex items-center justify-center rounded transition-colors hover:bg-white/5 flex-shrink-0"
        title={item.visible ? t("menu.hide", "隐藏") : t("menu.show", "显示")}
      >
        <span style={{ fontSize: 13, opacity: item.visible ? 1 : 0.3 }}>
          {item.visible ? "👁" : "👁‍🗨"}
        </span>
      </button>

      {/* 名称 */}
      <span className="flex-1 truncate">{t(item.i18nKey)}</span>

      {/* 排序按钮 */}
      <div className="flex flex-col gap-px flex-shrink-0">
        <button
          onClick={onMoveUp}
          disabled={isFirst}
          className="w-5 h-3.5 flex items-center justify-center rounded-t text-[9px] transition-opacity"
          style={{
            opacity: isFirst ? 0.2 : 0.5,
            color: "var(--txt-2)",
          }}
        >
          ▲
        </button>
        <button
          onClick={onMoveDown}
          disabled={isLast}
          className="w-5 h-3.5 flex items-center justify-center rounded-b text-[9px] transition-opacity"
          style={{
            opacity: isLast ? 0.2 : 0.5,
            color: "var(--txt-2)",
          }}
        >
          ▼
        </button>
      </div>
    </div>
  );
}

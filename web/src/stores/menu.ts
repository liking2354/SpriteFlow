import { create } from "zustand";

// ================================================================
// 菜单持久化接口 — 当前用 localStorage，未来可切到后端 API
// ================================================================

export interface MenuItem {
  id: string;
  to: string;
  i18nKey: string;
  section: "generate" | "manage";
  visible: boolean;
  order: number;
}

// ---- 持久化层抽象 ----
interface MenuPersistence {
  load(): Promise<MenuItem[]>;
  save(items: MenuItem[]): Promise<void>;
}

// ---- localStorage 实现（当前默认） ----
const STORAGE_KEY = "sf:menu";

const LocalStoragePersistence: MenuPersistence = {
  async load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return DEFAULT_ITEMS;
      const saved: Partial<MenuItem>[] = JSON.parse(raw);
      // 合并：保留已保存的配置，补齐新增项
      return DEFAULT_ITEMS.map((def) => {
        const savedItem = saved.find((s) => s.id === def.id);
        return savedItem ? { ...def, ...savedItem } : def;
      });
    } catch {
      return DEFAULT_ITEMS;
    }
  },
  async save(items: MenuItem[]) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  },
};

// ---- 后端 API 实现（多用户/权限场景时启用） ----
// 对应后端端点: GET/PUT /api/menu
// 数据存储在 configs 表中，key = "menu:items"
const APIPersistence: MenuPersistence = {
  async load() {
    const resp = await fetch("/api/menu");
    if (resp.status === 404) return DEFAULT_ITEMS;
    if (!resp.ok) throw new Error(`菜单加载失败: ${resp.status}`);
    const data = await resp.json();
    const saved: Partial<MenuItem>[] = data.items ?? [];
    return DEFAULT_ITEMS.map((def) => {
      const savedItem = saved.find((s: Partial<MenuItem>) => s.id === def.id);
      return savedItem ? { ...def, ...savedItem } : def;
    });
  },
  async save(items: MenuItem[]) {
    const resp = await fetch("/api/menu", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    if (!resp.ok) throw new Error(`菜单保存失败: ${resp.status}`);
  },
};

// ---- 默认项 ----
const DEFAULT_ITEMS: MenuItem[] = [
  { id: "generate",     to: "/",              i18nKey: "nav.generate",     section: "generate", visible: true, order: 0 },
  { id: "video",        to: "/video",        i18nKey: "nav.video",        section: "generate", visible: true, order: 1 },
  { id: "editor",       to: "/editor",       i18nKey: "nav.editor",       section: "generate", visible: true, order: 2 },
  { id: "spritesheet",  to: "/spritesheet",  i18nKey: "nav.spritesheet",  section: "generate", visible: true, order: 3 },
  { id: "videoFrames",  to: "/video-frames", i18nKey: "nav.videoFrames",  section: "generate", visible: true, order: 4 },
  { id: "assets",       to: "/assets",       i18nKey: "nav.assets",       section: "manage",   visible: true, order: 6 },
  { id: "routing",      to: "/routing",      i18nKey: "nav.routing",      section: "manage",   visible: true, order: 9 },
  { id: "workflow",     to: "/workflow",     i18nKey: "nav.workflow",     section: "manage",   visible: true, order: 10 },
  { id: "modelManager", to: "/model-manager", i18nKey: "nav.modelManager", section: "manage", visible: true, order: 11 },
  { id: "components",   to: "/components",    i18nKey: "nav.components",   section: "manage",   visible: true, order: 12 },
];

// ---- 切换开关（未来通过环境变量或配置控制） ----
let _persistence: MenuPersistence = LocalStoragePersistence;

export function useServerPersistence(backend: boolean) {
  _persistence = backend ? APIPersistence : LocalStoragePersistence;
}

// ---- Store ----
interface MenuState {
  items: MenuItem[];
  collapsed: boolean;
  settingsOpen: boolean;

  loadFromPersistence: () => Promise<void>;
  toggleItem: (id: string) => void;
  moveItem: (id: string, direction: "up" | "down") => void;
  toggleCollapsed: () => void;
  setSettingsOpen: (open: boolean) => void;
  resetDefaults: () => void;
}

async function persist(items: MenuItem[]) {
  try {
    await _persistence.save(items);
  } catch (e) {
    console.warn("[menu] 持久化失败:", e);
  }
}

export const useMenuStore = create<MenuState>((set, get) => ({
  items: DEFAULT_ITEMS, // 初始值，loadFromPersistence() 会覆盖
  collapsed: false,
  settingsOpen: false,

  loadFromPersistence: async () => {
    try {
      const items = await _persistence.load();
      set({ items });
    } catch (e) {
      console.warn("[menu] 加载菜单失败，使用默认配置:", e);
    }
  },

  toggleItem: (id) => {
    const items = get().items.map((it) =>
      it.id === id ? { ...it, visible: !it.visible } : it
    );
    persist(items);
    set({ items });
  },

  moveItem: (id, direction) => {
    const items = [...get().items];
    const idx = items.findIndex((it) => it.id === id);
    if (idx === -1) return;
    const targetIdx = direction === "up" ? idx - 1 : idx + 1;
    if (targetIdx < 0 || targetIdx >= items.length) return;
    if (items[idx].section !== items[targetIdx].section) return;
    [items[idx].order, items[targetIdx].order] = [items[targetIdx].order, items[idx].order];
    [items[idx], items[targetIdx]] = [items[targetIdx], items[idx]];
    persist(items);
    set({ items });
  },

  toggleCollapsed: () => {
    const next = !get().collapsed;
    set({ collapsed: next });
  },

  setSettingsOpen: (open) => set({ settingsOpen: open }),

  resetDefaults: () => {
    persist(DEFAULT_ITEMS);
    set({ items: DEFAULT_ITEMS });
  },
}));

import { create } from "zustand";

export type ThemeMode = "dark" | "light";
export type AccentColor = "blue" | "violet" | "cyan" | "pink" | "amber";

const STORAGE = {
  theme: "sf:theme",
  accent: "sf:accent",
};

function read<T extends string>(key: string, fallback: T): T {
  if (typeof localStorage === "undefined") return fallback;
  return (localStorage.getItem(key) as T) || fallback;
}

interface ThemeState {
  theme: ThemeMode;
  accent: AccentColor;
  setTheme: (t: ThemeMode) => void;
  setAccent: (a: AccentColor) => void;
  hydrate: () => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: read<ThemeMode>(STORAGE.theme, "dark"),
  accent: read<AccentColor>(STORAGE.accent, "blue"),

  setTheme: (theme) => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(STORAGE.theme, theme);
    set({ theme });
  },

  setAccent: (accent) => {
    document.documentElement.dataset.accent = accent;
    localStorage.setItem(STORAGE.accent, accent);
    set({ accent });
  },

  hydrate: () => {
    const theme = read<ThemeMode>(STORAGE.theme, "dark");
    const accent = read<AccentColor>(STORAGE.accent, "blue");
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.accent = accent;
    set({ theme, accent });
  },
}));

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zhCN from "./zh-CN.json";
import enUS from "./en-US.json";

const STORAGE_KEY = "sf:lang";

const stored =
  (typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY)) ||
  "zh-CN";

i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": { translation: zhCN },
    "en-US": { translation: enUS },
  },
  lng: stored,
  fallbackLng: "zh-CN",
  interpolation: { escapeValue: false },
});

export const supportedLngs = ["zh-CN", "en-US"] as const;
export type SupportedLng = (typeof supportedLngs)[number];

export function setLanguage(lng: SupportedLng) {
  i18n.changeLanguage(lng);
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(STORAGE_KEY, lng);
  }
  document.documentElement.lang = lng;
}

export default i18n;

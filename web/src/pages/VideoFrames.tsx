import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ExtractTab } from "@/pages/video-frames/ExtractTab";
import { GifTab } from "@/pages/video-frames/GifTab";
import { SpriteToolTab } from "@/pages/video-frames/SpriteToolTab";
import { PlayerTab } from "@/pages/video-frames/PlayerTab";
import { WatermarkTab } from "@/pages/video-frames/WatermarkTab";

const tabs = [
  { key: "extract", icon: "🎬", component: ExtractTab },
  { key: "gif", icon: "🔄", component: GifTab },
  { key: "spriteTool", icon: "🧩", component: SpriteToolTab },
  { key: "player", icon: "🎞", component: PlayerTab },
  { key: "watermark", icon: "🛡", component: WatermarkTab },
] as const;

export function VideoFramesPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<string>("extract");

  const ActiveComponent = tabs.find((tab) => tab.key === activeTab)?.component;

  return (
    <div style={{ padding: "24px 32px", height: "100%", overflowY: "auto" }}>
      {/* 标题区 */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--txt-1)", margin: 0 }}>
          {t("videoFrames.title")}
        </h1>
        <p style={{ fontSize: 13, color: "var(--txt-3)", marginTop: 4, marginBottom: 0 }}>
          {t("videoFrames.subtitle")}
        </p>
      </div>

      {/* 标签导航 */}
      <div
        style={{
          display: "flex",
          gap: 2,
          borderBottom: "1px solid var(--line)",
          marginBottom: 24,
          overflowX: "auto",
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "10px 20px",
              fontSize: 13,
              fontWeight: activeTab === tab.key ? 600 : 400,
              cursor: "pointer",
              border: "none",
              borderBottom: activeTab === tab.key ? "2px solid var(--acc)" : "2px solid transparent",
              background: "transparent",
              color: activeTab === tab.key ? "var(--acc)" : "var(--txt-2)",
              whiteSpace: "nowrap",
              transition: "color 0.15s, border-color 0.15s",
            }}
          >
            <span style={{ fontSize: 16 }}>{tab.icon}</span>
            {t(`videoFrames.tab${tab.key.charAt(0).toUpperCase() + tab.key.slice(1)}`)}
          </button>
        ))}
      </div>

      {/* 内容区 */}
      <div style={{ minHeight: 400 }}>
        {ActiveComponent ? <ActiveComponent /> : null}
      </div>
    </div>
  );
}

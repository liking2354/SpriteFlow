import { useEffect, useRef, type ReactNode } from "react";
import { TopBar } from "./TopBar";
import { SideNav } from "./SideNav";
import { StatusBar } from "./StatusBar";
import { useMenuStore } from "@/stores/menu";

export function AppShell({ children }: { children: ReactNode }) {
  const mainRef = useRef<HTMLElement | null>(null);
  const collapsed = useMenuStore((s) => s.collapsed);
  const sidebarWidth = collapsed ? 56 : 200;

  // 鼠标位置 → CSS 变量（聚光灯/网格遮罩跟随）
  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    let raf = 0;
    const onMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        el.style.setProperty("--mx", `${x}%`);
        el.style.setProperty("--my", `${y}%`);
      });
    };
    el.addEventListener("mousemove", onMove);
    return () => {
      el.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div className="grid h-screen relative" style={{ gridTemplateRows: "52px 1fr 30px" }}>
      <TopBar />
      <div className="grid overflow-hidden" style={{ gridTemplateColumns: `${sidebarWidth}px 1fr` }}>
        <SideNav />
        <main
          ref={mainRef}
          className="relative overflow-auto"
          style={{ background: "var(--bg-0)" }}
        >
          {/* 赛博点阵网格（鼠标聚光遮罩） */}
          <div className="tech-grid-bg" />

          {/* 极光 1：左上蓝 */}
          <div
            className="aurora-orb"
            style={{
              top: -120,
              left: "22%",
              width: 460,
              height: 460,
              background: "var(--acc)",
              opacity: 0.18,
              animation: "aurora-drift 18s ease-in-out infinite",
            }}
          />
          {/* 极光 2：右下紫 */}
          <div
            className="aurora-orb"
            style={{
              bottom: -100,
              right: "10%",
              width: 380,
              height: 380,
              background: "var(--violet)",
              opacity: 0.15,
              animation: "aurora-drift-2 22s ease-in-out infinite",
            }}
          />
          {/* 极光 3：中下青 */}
          <div
            className="aurora-orb"
            style={{
              bottom: 80,
              left: "55%",
              width: 280,
              height: 280,
              background: "var(--cyan)",
              opacity: 0.08,
              animation: "aurora-drift 26s ease-in-out infinite",
            }}
          />

          {/* 顶部 hairline 高光 */}
          <div
            className="absolute top-0 left-0 right-0 h-px pointer-events-none"
            style={{
              background:
                "linear-gradient(90deg, transparent 5%, rgba(var(--acc-rgb), 0.35) 50%, transparent 95%)",
              opacity: 0.6,
            }}
          />

          <div className="relative z-10 p-6 h-full">{children}</div>
        </main>
      </div>
      <StatusBar />
    </div>
  );
}

import type { ReactNode } from "react";
import { TopBar } from "./TopBar";
import { SideNav } from "./SideNav";
import { StatusBar } from "./StatusBar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid h-screen" style={{ gridTemplateRows: "52px 1fr 30px" }}>
      <TopBar />
      <div className="grid overflow-hidden" style={{ gridTemplateColumns: "200px 1fr" }}>
        <SideNav />
        <main className="relative overflow-auto bg-bg-0">
          {/* 装饰性辉光 */}
          <div
            className="pointer-events-none absolute"
            style={{
              top: -100,
              left: "30%",
              width: 340,
              height: 340,
              filter: "blur(80px)",
              opacity: 0.15,
              borderRadius: "50%",
              background: "var(--acc)",
              zIndex: 0,
            }}
          />
          <div
            className="pointer-events-none absolute"
            style={{
              bottom: -60,
              right: "15%",
              width: 280,
              height: 280,
              filter: "blur(80px)",
              opacity: 0.13,
              borderRadius: "50%",
              background: "var(--violet)",
              zIndex: 0,
            }}
          />
          <div className="relative z-10 p-6">{children}</div>
        </main>
      </div>
      <StatusBar />
    </div>
  );
}

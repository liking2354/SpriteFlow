import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { Pill } from "../ui/Pill";
import { ThemeSwitcher } from "../ui/ThemeSwitcher";

export function TopBar() {
  const { t } = useTranslation();
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15000,
  });

  const online = !!data && !isError && data.ark_configured;

  return (
    <header
      className="relative h-[52px] px-5 flex items-center gap-5 border-b border-line glass-strong"
      style={{
        background:
          "linear-gradient(180deg, var(--bg-2) 0%, var(--bg-1) 100%)",
      }}
    >
      {/* 顶部 1px 渐变光线 */}
      <div
        className="absolute bottom-0 left-0 right-0 h-px pointer-events-none"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(var(--acc-rgb), 0.45) 30%, rgba(var(--acc-rgb), 0.45) 70%, transparent)",
          opacity: 0.7,
        }}
      />

      <Link to="/" className="flex items-center gap-3 font-semibold text-[15px] text-txt-0 group">
        <div className="tech-mark group-hover:scale-[1.03] transition-transform" />
        <div className="flex items-baseline gap-1.5 leading-none">
          <span className="font-semibold tracking-[0.5px]">SpriteFlow</span>
          <span
            className="text-[10px] text-txt-3 font-mono uppercase tracking-[1px]"
            style={{ letterSpacing: "1.2px" }}
          >
            v0.1
          </span>
        </div>
      </Link>

      {data && (
        <div className="hidden md:flex items-center gap-2 text-[11px] text-txt-2 font-mono pl-4 border-l border-[var(--line-soft)]">
          <span className="text-txt-3 uppercase tracking-[1.2px] text-[10px]">
            {t("topbar.modelLabel")}
          </span>
          <span className="text-txt-1">{data.model}</span>
        </div>
      )}

      <div className="ml-auto flex items-center gap-2.5">
        <Pill glow={online ? "green" : "red"}>
          {online ? t("topbar.engineOnline") : t("topbar.engineOffline")}
        </Pill>
        <ThemeSwitcher />
      </div>
    </header>
  );
}

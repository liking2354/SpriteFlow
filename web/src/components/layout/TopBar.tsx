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
    <header className="h-[52px] px-5 flex items-center gap-5 border-b border-line"
      style={{ background: "linear-gradient(180deg, var(--bg-2), var(--bg-1))" }}
    >
      <Link to="/" className="flex items-center gap-2.5 font-semibold text-[15px] text-txt-0">
        <div
          className="relative w-[26px] h-[26px] rounded-s"
          style={{
            background: "linear-gradient(135deg, var(--acc), var(--violet))",
            boxShadow: "0 0 16px var(--acc-glow)",
          }}
        >
          <span
            className="absolute inset-[7px] rounded-[3px]"
            style={{ background: "var(--bg-1)" }}
          />
        </div>
        SpriteFlow
        <span className="text-[11px] text-txt-2 font-normal ml-1">v0.1</span>
      </Link>

      {data && (
        <div className="flex items-center gap-2 text-[11.5px] text-txt-2 font-mono">
          <span>{t("topbar.modelLabel")}</span>
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

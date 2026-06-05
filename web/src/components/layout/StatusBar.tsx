import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { Led } from "../ui/Led";

export function StatusBar() {
  const { t } = useTranslation();
  const { data: nodes } = useQuery({
    queryKey: ["nodes-count"],
    queryFn: api.listNodes,
    staleTime: 60_000,
  });
  const { data: assets } = useQuery({
    queryKey: ["assets-count"],
    queryFn: () => api.listAssets({ limit: 1 }),
    refetchInterval: 30_000,
  });
  const { data: routing } = useQuery({
    queryKey: ["routing"],
    queryFn: api.getRouting,
    staleTime: 60_000,
  });

  return (
    <footer
      className="relative h-[30px] px-4 flex items-center gap-5 border-t border-line text-[11px] text-txt-2 font-mono"
      style={{ background: "var(--bg-1)" }}
    >
      {/* 顶部 1px 渐变光线 */}
      <div
        className="absolute top-0 left-0 right-0 h-px pointer-events-none"
        style={{
          background:
            "linear-gradient(90deg, transparent, rgba(var(--acc-rgb), 0.4) 50%, transparent)",
          opacity: 0.6,
        }}
      />

      <span className="flex items-center gap-1.5">
        <Led color="green" size={6} />
        <span className="uppercase tracking-[1px]">{t("status.ok")}</span>
      </span>
      <Stat label="nodes" value={nodes?.length ?? "-"} />
      <Stat label="assets" value={assets?.total ?? "-"} />
      <Stat
        label="routes"
        value={routing ? Object.keys(routing.routes).length : "-"}
      />

      <span className="ml-auto flex items-center gap-2 text-txt-3 uppercase tracking-[1.2px] text-[10px]">
        <span
          className="w-1 h-1 rounded-full"
          style={{
            background: "var(--acc)",
            boxShadow: "0 0 5px var(--acc)",
          }}
        />
        SpriteFlow Engine
      </span>
    </footer>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-txt-3 uppercase text-[10px] tracking-[1px]">
        {label}
      </span>
      <span className="text-txt-1">{String(value)}</span>
    </span>
  );
}

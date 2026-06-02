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
    <footer className="h-[30px] px-4 flex items-center gap-5 bg-bg-1 border-t border-line text-[11px] text-txt-2 font-mono">
      <span className="flex items-center gap-1.5">
        <Led color="green" size={6} /> {t("status.ok")}
      </span>
      <span>nodes: {nodes?.length ?? "-"}</span>
      <span>assets: {assets?.total ?? "-"}</span>
      <span>routes: {routing ? Object.keys(routing.routes).length : "-"}</span>
      <span className="ml-auto text-txt-3">SpriteFlow Engine</span>
    </footer>
  );
}

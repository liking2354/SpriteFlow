import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { Led } from "@/components/ui/Led";

export function RoutingPage() {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["routing"],
    queryFn: api.getRouting,
  });

  return (
    <div className="grid grid-cols-12 gap-5 max-w-[1200px]">
      <div className="col-span-12 lg:col-span-7">
        <Card
          title={t("routing.title")}
          subtitle={t("routing.subtitle")}
        >
          {isLoading && (
            <div className="text-center py-12 text-txt-3">{t("common.loading")}</div>
          )}
          {data && (
            <>
              <div className="text-[10.5px] text-txt-3 uppercase tracking-[1px] mb-3">
                {t("routing.currentRoutes")}
              </div>
              <div className="grid grid-cols-1 gap-2">
                {Object.entries(data.routes).map(([cap, prov]) => (
                  <div
                    key={cap}
                    className="flex items-center gap-3 px-3 py-2.5 bg-bg-0 border border-[var(--line-soft)] rounded-s"
                  >
                    <span className="text-[12px] text-txt-1 font-medium min-w-[180px]">
                      {t(`routing.capabilityNames.${cap}`, { defaultValue: cap })}
                    </span>
                    <span className="text-txt-3 font-mono text-[11px]">→</span>
                    <span
                      className="ml-auto px-2.5 h-6 flex items-center rounded-s font-mono text-[11px]"
                      style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
                    >
                      {prov}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      <div className="col-span-12 lg:col-span-5">
        <Card title={t("routing.providers")}>
          {data?.providers.map((p) => (
            <div
              key={p.name}
              className="px-3 py-3 bg-bg-0 border border-[var(--line-soft)] rounded-s mb-2"
            >
              <div className="flex items-center gap-2">
                <Led color="green" size={7} />
                <span className="text-[13px] font-semibold text-txt-0">{p.name}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {p.capabilities.map((c) => (
                  <span
                    key={c}
                    className="px-2 py-0.5 rounded font-mono text-[10px] text-txt-1 bg-bg-3 border border-line"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

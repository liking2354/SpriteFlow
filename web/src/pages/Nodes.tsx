import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/Card";

const CATEGORY_COLOR: Record<string, string> = {
  generate: "var(--acc)",
  process: "var(--pink)",
  pixel: "var(--amber)",
  flow: "var(--violet)",
  export: "var(--green)",
  uncategorized: "var(--txt-3)",
};

export function NodesPage() {
  const { t } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["nodes"],
    queryFn: api.listNodes,
  });

  // 按 category 分组
  const grouped = (data || []).reduce<Record<string, typeof data>>((acc, n) => {
    const k = n.category || "uncategorized";
    if (!acc[k]) acc[k] = [] as never;
    (acc[k] as never[]).push(n as never);
    return acc;
  }, {});

  return (
    <div className="max-w-[1300px]">
      <div className="mb-5">
        <h2 className="text-[16px] font-semibold text-txt-0 mb-1">
          {t("nodes.title")}
        </h2>
        <p className="text-[12px] text-txt-2">{t("nodes.subtitle")}</p>
      </div>

      {isLoading && (
        <div className="text-center py-12 text-txt-3">{t("common.loading")}</div>
      )}

      {Object.entries(grouped).map(([cat, list]) => (
        <div key={cat} className="mb-6">
          <div className="text-[10.5px] uppercase tracking-[1.2px] text-txt-3 font-semibold mb-3 flex items-center gap-2">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: CATEGORY_COLOR[cat] || CATEGORY_COLOR.uncategorized }}
            />
            {t(`nodes.category.${cat}`, { defaultValue: cat })}
            <span className="text-txt-3 font-mono">({(list || []).length})</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(list || []).map((n) => (
              <Card key={n.type} className="!p-0" glass>
                <div
                  className="px-4 pt-3 pb-2 border-b border-[var(--line-soft)] flex items-center gap-2"
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: CATEGORY_COLOR[cat] }}
                  />
                  <span className="text-[12.5px] font-semibold text-txt-0">
                    {n.type}
                  </span>
                  <span className="ml-auto text-[9.5px] font-mono text-txt-2 px-1.5 py-0.5 rounded bg-bg-0">
                    {n.category}
                  </span>
                </div>

                <div className="p-4 space-y-3">
                  <PortRow title={t("nodes.inputs")} ports={n.inputs} />
                  <PortRow title={t("nodes.outputs")} ports={n.outputs} />
                  {n.params.length > 0 && (
                    <div>
                      <div className="text-[10px] text-txt-3 uppercase tracking-[1px] mb-1.5">
                        {t("nodes.params")}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {n.params.map((p) => (
                          <span
                            key={p.name}
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-bg-0 border border-line text-txt-1"
                          >
                            {p.name}
                            <span className="text-txt-3">:</span>
                            {p.type}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PortRow({
  title,
  ports,
}: {
  title: string;
  ports: Record<string, string>;
}) {
  const entries = Object.entries(ports);
  if (entries.length === 0) return null;
  return (
    <div>
      <div className="text-[10px] text-txt-3 uppercase tracking-[1px] mb-1.5">
        {title}
      </div>
      <div className="flex flex-wrap gap-1">
        {entries.map(([name, type]) => (
          <span
            key={name}
            className="text-[10px] font-mono px-1.5 py-0.5 rounded text-txt-0"
            style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
          >
            {name}
            <span className="opacity-50">:</span>
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}

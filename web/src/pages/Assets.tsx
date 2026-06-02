import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Segment } from "@/components/ui/Segment";
import { TextInput } from "@/components/ui/Field";

type SourceFilter = "all" | "uploaded" | "generated" | "derived";

export function AssetsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [source, setSource] = useState<SourceFilter>("all");
  const [tagsFilter, setTagsFilter] = useState("");
  const [selected, setSelected] = useState<AssetItem | null>(null);

  const list = useQuery({
    queryKey: ["assets", source, tagsFilter],
    queryFn: () =>
      api.listAssets({
        source: source === "all" ? undefined : source,
        tags: tagsFilter || undefined,
        limit: 50,
      }),
  });

  const upload = useMutation({
    mutationFn: ({ file, tags }: { file: File; tags: string }) =>
      api.uploadAsset(file, tags),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["assets"] }),
  });

  const del = useMutation({
    mutationFn: (id: string) => api.deleteAsset(id),
    onSuccess: () => {
      setSelected(null);
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    upload.mutate({ file: f, tags: "" });
    e.target.value = "";
  };

  return (
    <div className="grid grid-cols-12 gap-5 max-w-[1500px]">
      <div className={selected ? "col-span-12 lg:col-span-8" : "col-span-12"}>
        <Card
          title={t("assets.title")}
          subtitle={t("assets.subtitle")}
          actions={
            <>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={onFile}
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() => fileRef.current?.click()}
                loading={upload.isPending}
              >
                ↑ {t("assets.upload.button")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => list.refetch()}>
                ⟳ {t("common.refresh")}
              </Button>
            </>
          }
        >
          <div className="flex items-center gap-3 mb-4">
            <Segment
              items={[
                { value: "all", label: t("assets.filter.all") },
                { value: "uploaded", label: t("assets.filter.uploaded") },
                { value: "generated", label: t("assets.filter.generated") },
                { value: "derived", label: t("assets.filter.derived") },
              ]}
              value={source}
              onChange={setSource}
              className="flex-shrink-0 w-[360px]"
            />
            <div className="flex-1">
              <TextInput
                value={tagsFilter}
                onChange={(e) => setTagsFilter(e.target.value)}
                placeholder={t("assets.filter.tagsPlaceholder")}
              />
            </div>
          </div>

          {list.isLoading && (
            <div className="text-center py-12 text-txt-3">{t("common.loading")}</div>
          )}

          {list.data && list.data.items.length === 0 && (
            <div className="text-center py-12 text-txt-3">{t("assets.empty")}</div>
          )}

          {list.data && list.data.items.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
              {list.data.items.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setSelected(a)}
                  className={`group relative aspect-square overflow-hidden rounded-m border bg-bg-0 transition-all ${
                    selected?.id === a.id
                      ? "border-[var(--acc)]"
                      : "border-line hover:border-[#2f3647]"
                  }`}
                >
                  {a.thumbnail || a.uri ? (
                    <img
                      src={a.thumbnail || a.uri}
                      alt={a.id}
                      className="w-full h-full object-cover pixelated"
                    />
                  ) : (
                    <div className="w-full h-full grid place-items-center text-txt-3 text-[10px]">
                      no preview
                    </div>
                  )}
                  <div className="absolute top-1.5 left-1.5">
                    <span
                      className="text-[8.5px] font-mono px-1.5 py-0.5 rounded text-white"
                      style={{
                        background:
                          a.source === "uploaded"
                            ? "var(--cyan)"
                            : a.source === "generated"
                            ? "var(--acc)"
                            : "var(--violet)",
                        color: "#001",
                      }}
                    >
                      {a.source}
                    </span>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 px-2 py-1 bg-gradient-to-t from-black/80 text-[9.5px] font-mono text-white text-left">
                    {a.width}×{a.height}
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      {selected && (
        <div className="col-span-12 lg:col-span-4">
          <Card
            title={t("assets.detail.title")}
            actions={
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSelected(null)}
              >
                ✕
              </Button>
            }
          >
            <img
              src={selected.uri}
              alt={selected.id}
              className="w-full rounded-m mb-4 pixelated border border-line"
            />
            <Detail label={t("assets.detail.id")} value={selected.id} mono />
            <Detail label={t("assets.detail.type")} value={selected.type} />
            <Detail label={t("assets.detail.source")} value={selected.source} />
            <Detail
              label={t("assets.detail.size")}
              value={`${selected.width ?? "-"} × ${selected.height ?? "-"}`}
            />
            <Detail label={t("assets.detail.hash")} value={selected.hash} mono />
            <Detail
              label={t("assets.detail.tags")}
              value={
                <div className="flex flex-wrap gap-1.5">
                  {selected.tags.length === 0 && (
                    <span className="text-txt-3 text-[11px]">—</span>
                  )}
                  {selected.tags.map((tg) => (
                    <span
                      key={tg}
                      className="px-2 py-0.5 rounded-full bg-bg-3 border border-line text-[10px] font-mono text-txt-1"
                    >
                      {tg}
                    </span>
                  ))}
                </div>
              }
            />
            <Detail
              label={t("assets.detail.createdAt")}
              value={selected.created_at}
              mono
            />

            {selected.parent_id && (
              <Detail
                label={t("assets.detail.parent")}
                value={selected.parent_id}
                mono
              />
            )}

            {selected.provenance && (
              <Detail
                label={t("assets.detail.provenance")}
                value={
                  <pre className="text-[10.5px] text-txt-2 whitespace-pre-wrap break-all">
                    {JSON.stringify(selected.provenance, null, 2)}
                  </pre>
                }
              />
            )}

            <div className="mt-5 flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  navigator.clipboard.writeText(selected.id);
                }}
              >
                {t("common.copy")} ID
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => del.mutate(selected.id)}
                loading={del.isPending}
              >
                {t("common.delete")}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function Detail({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="mb-3">
      <div className="text-[10.5px] text-txt-3 uppercase tracking-[1px] mb-1">
        {label}
      </div>
      <div
        className={`text-[12px] text-txt-1 break-all ${mono ? "font-mono" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

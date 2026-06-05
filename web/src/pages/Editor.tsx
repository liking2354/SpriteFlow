/**
 * /editor — 独立素材编辑器页面
 *
 * 行为：
 *  - URL 参数 `?asset=ID` 直接加载该素材进入编辑（来自 ImagePreview/Assets 页跳转）
 *  - URL 参数 `?url=...&parent=...` 直接加载远程图片
 *  - 没有参数时显示"选图工作台"：可上传本地图 / 从素材库选取
 *
 * 保存后：自动建立 parent_id 血缘，并把当前编辑目标切换到刚保存的新素材，
 *         方便链式编辑（抠图 → 再裁剪 → 再保存）。
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Segment } from "@/components/ui/Segment";
import { AssetEditor } from "@/components/AssetEditor";

interface EditorTarget {
  url: string;
  assetId?: string | null;
  /** 仅展示用：图片名/ID */
  label?: string;
}

export function EditorPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [target, setTarget] = useState<EditorTarget | null>(null);
  const [pickerSource, setPickerSource] = useState<"all" | "uploaded" | "generated" | "derived">("all");

  // ===== 1. 从 URL 参数还原 target =====
  const assetParam = searchParams.get("asset");
  const urlParam = searchParams.get("url");
  const parentParam = searchParams.get("parent");

  // 当 ?asset=xx 时，先取 asset 详情拿预签名 URL
  const assetQuery = useQuery({
    queryKey: ["asset-detail", assetParam],
    queryFn: () => api.getAsset(assetParam!),
    enabled: !!assetParam,
  });

  useEffect(() => {
    if (assetParam && assetQuery.data) {
      setTarget({
        url: assetQuery.data.uri,
        assetId: assetQuery.data.id,
        label: assetQuery.data.id,
      });
    } else if (urlParam && !assetParam) {
      setTarget({
        url: urlParam,
        assetId: parentParam || null,
        label: parentParam || urlParam.slice(0, 24),
      });
    }
  }, [assetParam, assetQuery.data, urlParam, parentParam]);

  // ===== 2. 选图：素材库 =====
  const list = useQuery({
    queryKey: ["editor-assets", pickerSource],
    queryFn: () =>
      api.listAssets({
        source: pickerSource === "all" ? undefined : pickerSource,
        limit: 60,
      }),
    enabled: !target, // 仅在未选图时拉取
  });

  // ===== 3. 选图：上传 =====
  const upload = useMutation({
    mutationFn: ({ file }: { file: File }) => api.uploadAsset(file, "uploaded"),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ["editor-assets"] });
      // 上传完直接进入编辑
      navigateToAsset(asset);
    },
  });

  const onLocalFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    upload.mutate({ file: f });
    e.target.value = "";
  };

  // ===== 4. 切换 / 退出编辑目标 =====
  const navigateToAsset = (asset: AssetItem) => {
    setSearchParams({ asset: asset.id }, { replace: false });
    setTarget({ url: asset.uri, assetId: asset.id, label: asset.id });
  };

  const clearTarget = () => {
    setSearchParams({}, { replace: false });
    setTarget(null);
  };

  // 保存成功后：URL 切到新素材，继续可编辑
  const handleSaved = (asset: AssetItem) => {
    setSearchParams({ asset: asset.id }, { replace: true });
    setTarget({ url: asset.uri, assetId: asset.id, label: asset.id });
  };

  // ===== 渲染 =====

  // 模式 A：未选图 → 工作台（上传 + 素材库）
  if (!target) {
    return (
      <div className="max-w-[1500px]">
        <Card
          title={t("editor.title")}
          subtitle={t("editor.pickerSubtitle")}
          actions={
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={onLocalFile}
              />
              <Button
                size="sm"
                variant="primary"
                onClick={() => fileInputRef.current?.click()}
                loading={upload.isPending}
              >
                ↑ {t("editor.uploadLocal")}
              </Button>
            </>
          }
        >
          {/* 大上传区 */}
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) upload.mutate({ file: f });
            }}
            className="mb-5 cursor-pointer rounded-l border-2 border-dashed border-line hover:border-[var(--acc)] hover:bg-[var(--acc-soft)]/40 transition-colors py-12 grid place-items-center text-center"
          >
            <div className="text-[24px] mb-2 opacity-60">⬆</div>
            <div className="text-[13px] text-txt-1 font-medium mb-1">
              {t("editor.dropTitle")}
            </div>
            <div className="text-[11.5px] text-txt-3">{t("editor.dropHint")}</div>
          </div>

          {/* 素材库选择器 */}
          <div className="flex items-center justify-between mb-3">
            <div className="text-[12px] text-txt-1 font-medium">
              {t("editor.fromLibrary")}
            </div>
            <Segment
              items={[
                { value: "all", label: t("assets.filter.all") },
                { value: "uploaded", label: t("assets.filter.uploaded") },
                { value: "generated", label: t("assets.filter.generated") },
                { value: "derived", label: t("assets.filter.derived") },
              ]}
              value={pickerSource}
              onChange={(v) => setPickerSource(v as typeof pickerSource)}
              className="!w-[400px]"
            />
          </div>

          {list.isLoading && (
            <div className="text-center py-12 text-txt-3 text-[12px]">
              {t("common.loading")}
            </div>
          )}

          {list.data && list.data.items.length === 0 && (
            <div className="text-center py-12 text-txt-3 text-[12px]">
              {t("assets.empty")}
            </div>
          )}

          {list.data && list.data.items.length > 0 && (
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2.5">
              {list.data.items.map((a) => (
                <button
                  key={a.id}
                  onClick={() => navigateToAsset(a)}
                  className="group relative aspect-square overflow-hidden rounded-s border border-line bg-bg-0 hover:border-[var(--acc)] transition-colors"
                  title={a.id}
                >
                  <img
                    src={a.thumbnail || a.uri}
                    alt=""
                    className="w-full h-full object-cover pixelated"
                  />
                  <div className="absolute inset-x-0 bottom-0 px-1.5 py-1 bg-gradient-to-t from-black/80 text-[9px] font-mono text-white">
                    {a.width}×{a.height}
                  </div>
                  <div className="absolute inset-0 grid place-items-center bg-black/0 group-hover:bg-black/40 transition-colors opacity-0 group-hover:opacity-100">
                    <span className="text-white text-[11px] font-medium">
                      ✎ {t("editor.open")}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    );
  }

  // 模式 B：已有 target → 全屏编辑
  return (
    <div className="max-w-[1500px] flex flex-col" style={{ height: "calc(100vh - 130px)" }}>
      {/* 顶部工具条 */}
      <div className="flex items-center gap-3 mb-3 flex-shrink-0">
        <Button size="sm" variant="ghost" onClick={() => navigate(-1)}>
          ← {t("common.cancel")}
        </Button>
        <div className="text-[13px] text-txt-0 font-medium">
          {t("editor.title")}
        </div>
        {target.label && (
          <span
            className="px-2 py-0.5 rounded bg-bg-3 border border-line text-[10.5px] font-mono text-txt-2"
            title={target.label}
          >
            {target.label.length > 28 ? target.label.slice(0, 28) + "…" : target.label}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={clearTarget}>
            ⇆ {t("editor.changeTarget")}
          </Button>
        </div>
      </div>

      {/* 编辑器内核 */}
      <div className="flex-1 min-h-0">
        <AssetEditor
          key={target.url}
          url={target.url}
          parentAssetId={target.assetId || undefined}
          onSaved={handleSaved}
        />
      </div>
    </div>
  );
}

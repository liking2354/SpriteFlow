import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AssetItem } from "@/api/types";
import { AssetPicker } from "./AssetPicker";

/** 一张参考图条目（统一表示，便于 chip 展示） */
export interface RefImage {
  /** 显示用 URL（本地上传或素材库的预签名链接） */
  url: string;
  /** 缩略图 URL（用于卡片预览） */
  thumbnail?: string | null;
  /** 来自素材库时附带的 asset_id（前端透传到后端 ref_asset_ids） */
  asset_id?: string;
  /** 来源类型，用于 chip 标签 */
  origin: "upload" | "asset" | "url";
  /** 原始文件名（仅 upload 时） */
  name?: string;
}

interface Props {
  values: RefImage[];
  max: number;                         // 最大可加图数
  onChange: (next: RefImage[]) => void;
}

export function RefImagePicker({ values, max, onChange }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [urlInput, setUrlInput] = useState("");

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const asset = await api.uploadAsset(file, "uploaded:reference");
      // 拿到预签名 URL（直接用 thumbnail 或 uri）
      return asset;
    },
    onSuccess: (asset: AssetItem) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      const next: RefImage = {
        url: asset.uri,
        thumbnail: asset.thumbnail,
        asset_id: asset.id,
        origin: "upload",
        name: asset.id,
      };
      onChange([...values, next]);
    },
  });

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    upload.mutate(f);
    e.target.value = "";
  };

  const addUrl = () => {
    const url = urlInput.trim();
    if (!url) return;
    onChange([
      ...values,
      { url, thumbnail: url, origin: "url" },
    ]);
    setUrlInput("");
  };

  const onPickAsset = (a: AssetItem) => {
    onChange([
      ...values,
      {
        url: a.uri,
        thumbnail: a.thumbnail || a.uri,
        asset_id: a.id,
        origin: "asset",
      },
    ]);
  };

  const remove = (i: number) =>
    onChange(values.filter((_, idx) => idx !== i));

  const reachedMax = values.length >= max;

  return (
    <div>
      {/* 已选缩略图条 */}
      {values.length > 0 && (
        <div className="grid grid-cols-4 gap-2 mb-3">
          {values.map((v, i) => (
            <div
              key={i}
              className="relative group aspect-square rounded-s overflow-hidden border border-line bg-bg-0"
            >
              <img
                src={v.thumbnail || v.url}
                alt=""
                className="w-full h-full object-cover pixelated"
              />
              <button
                onClick={() => remove(i)}
                className="absolute top-1 right-1 w-5 h-5 grid place-items-center rounded-full bg-black/60 hover:bg-black/80 text-white text-[12px]"
              >
                ✕
              </button>
              <span
                className="absolute bottom-1 left-1 text-[8.5px] font-mono px-1 py-0.5 rounded text-black"
                style={{
                  background:
                    v.origin === "asset"
                      ? "var(--violet)"
                      : v.origin === "upload"
                      ? "var(--cyan)"
                      : "var(--amber)",
                }}
              >
                {v.origin === "asset" ? "ASSET" : v.origin === "upload" ? "LOCAL" : "URL"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* 三种添加方式 */}
      {!reachedMax && (
        <>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={onFile}
          />
          <div className="grid grid-cols-2 gap-2 mb-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={upload.isPending}
              className="flex items-center justify-center gap-1.5 h-9 rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:border-[#2f3647] hover:text-txt-0 disabled:opacity-50"
            >
              <span>↑</span>
              {upload.isPending ? t("common.loading") : t("ref.uploadLocal")}
            </button>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex items-center justify-center gap-1.5 h-9 rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:border-[#2f3647] hover:text-txt-0"
            >
              <span>📚</span>
              {t("ref.fromLibrary")}
            </button>
          </div>
          <div className="flex gap-2">
            <input
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addUrl();
                }
              }}
              placeholder={t("ref.urlPlaceholder")}
              className="flex-1 px-3 h-9 bg-bg-0 border border-line rounded-s text-[12px] text-txt-1 font-mono outline-none focus:border-[var(--acc)]"
            />
            <button
              type="button"
              onClick={addUrl}
              className="h-9 px-3 rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:border-[#2f3647] hover:text-txt-0"
            >
              + URL
            </button>
          </div>
        </>
      )}

      <div className="mt-2 text-[10.5px] text-txt-3 font-mono">
        {values.length}/{max}
      </div>

      <AssetPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={onPickAsset}
      />
    </div>
  );
}

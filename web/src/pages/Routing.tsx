import { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { RoutingResponse, ProviderConfig } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Led } from "@/components/ui/Led";
import { Field, Select, TextInput } from "@/components/ui/Field";

/** 所有已知 capability 的中文标签 */
const CAPABILITY_LABELS: Record<string, string> = {
  text2img: "文生图",
  img2img: "图生图",
  multi_image_fusion: "多图融合",
  sequential_images: "组图生成",
  text2video: "文生视频",
  img2video: "图生视频",
  remove_bg: "去背景",
  extract_frames: "视频抽帧",
  character_master: "角色母版",
  four_view: "四视图",
  enhance_photo: "画质增强",
  image_inpaint: "擦除修复",
  image_outpaint: "智能扩图",
  image_cut: "智能裁剪",
  slim_image: "集智瘦身",
  resize_image: "图像缩放",
};

export function RoutingPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  // ----- data -----
  const { data, isLoading } = useQuery({
    queryKey: ["routing"],
    queryFn: api.getRouting,
  });
  const { data: configData } = useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
  });

  // ----- local edit state (routing) -----
  const [editRoutes, setEditRoutes] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);

  const providerList = useMemo(() => {
    return data?.providers.map((p) => p.name) ?? [];
  }, [data]);

  const initEdit = useCallback(
    (r: RoutingResponse) => {
      setEditRoutes({ ...r.routes });
      setDirty(false);
    },
    []
  );

  // init once
  useMemo(() => {
    if (data && !Object.keys(editRoutes).length) initEdit(data);
  }, [data, editRoutes, initEdit]);

  const handleRouteChange = (cap: string, prov: string) => {
    setEditRoutes((prev) => ({ ...prev, [cap]: prov }));
    setDirty(true);
  };

  // ----- save routing mutation -----
  const saveRouting = useMutation({
    mutationFn: (routes: Record<string, string>) =>
      api.updateRouting({ routes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["routing"] });
      setDirty(false);
    },
  });

  const reloadRouting = useMutation({
    mutationFn: api.reloadRouting,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["routing"] });
      setDirty(false);
    },
  });

  // ----- OpenRouter config edit state -----
  const [orModel, setOrModel] = useState("");
  const [orBaseUrl, setOrBaseUrl] = useState("");
  const [orApiKey, setOrApiKey] = useState("");
  const [orDirty, setOrDirty] = useState(false);

  const openrouterCfg = configData?.providers?.openrouter as
    | ProviderConfig
    | undefined;

  useEffect(() => {
    if (openrouterCfg && !orModel) {
      setOrModel(openrouterCfg.model || "");
      setOrBaseUrl(openrouterCfg.base_url || "");
      setOrApiKey("");
      setOrDirty(false);
    }
  }, [openrouterCfg, orModel]);

  const handleOrFieldChange = (
    setter: (v: string) => void,
    val: string
  ) => {
    setter(val);
    setOrDirty(true);
  };

  const saveOpenRouter = useMutation({
    mutationFn: () =>
      api.updateConfig({
        providers: {
          openrouter: {
            model: orModel || undefined,
            base_url: orBaseUrl || undefined,
            api_key: orApiKey || undefined,
          },
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      setOrApiKey("");
      setOrDirty(false);
    },
  });

  // also save Seedream/Seedance config
  const [sdModel, setSdModel] = useState("");
  const [sdBaseUrl, setSdBaseUrl] = useState("");
  const [sdDirty, setSdDirty] = useState(false);
  const seedreamCfg = configData?.providers?.seedream as
    | ProviderConfig
    | undefined;

  useEffect(() => {
    if (seedreamCfg && !sdModel) {
      setSdModel(seedreamCfg.model || "");
      setSdBaseUrl(seedreamCfg.base_url || "");
      setSdDirty(false);
    }
  }, [seedreamCfg, sdModel]);

  const saveSeedream = useMutation({
    mutationFn: () =>
      api.updateConfig({
        providers: {
          seedream: {
            model: sdModel || undefined,
            base_url: sdBaseUrl || undefined,
          },
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      setSdDirty(false);
    },
  });

  // seedance
  const [sdaModel, setSdaModel] = useState("");
  const [sdaBaseUrl, setSdaBaseUrl] = useState("");
  const [sdaDirty, setSdaDirty] = useState(false);
  const seedanceCfg = configData?.providers?.seedance as
    | ProviderConfig
    | undefined;

  useEffect(() => {
    if (seedanceCfg && !sdaModel) {
      setSdaModel(seedanceCfg.model || "");
      setSdaBaseUrl(seedanceCfg.base_url || "");
      setSdaDirty(false);
    }
  }, [seedanceCfg, sdaModel]);

  const saveSeedance = useMutation({
    mutationFn: () =>
      api.updateConfig({
        providers: {
          seedance: {
            model: sdaModel || undefined,
            base_url: sdaBaseUrl || undefined,
          },
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      setSdaDirty(false);
    },
  });

  // ----- render -----
  return (
    <div className="flex flex-col gap-5 max-w-[1000px]">
      {/* ====== Route Map ====== */}
      <Card
        title={t("routing.title")}
        subtitle={t("routing.subtitle")}
        actions={
          <div className="flex items-center gap-2">
            {dirty && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => data && initEdit(data)}
              >
                {t("common.cancel")}
              </Button>
            )}
            <Button
              size="xs"
              variant="outline"
              loading={reloadRouting.isPending}
              onClick={() => reloadRouting.mutate()}
            >
              ↻ {t("routing.reload", { defaultValue: "重新加载" })}
            </Button>
            <Button
              size="sm"
              loading={saveRouting.isPending}
              disabled={!dirty}
              onClick={() => saveRouting.mutate(editRoutes)}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        {isLoading && (
          <div className="text-center py-10 text-txt-3">
            {t("common.loading")}
          </div>
        )}
        {data && (
          <div className="grid grid-cols-1 gap-1.5">
            {/* table header */}
            <div className="flex items-center gap-3 px-2 py-1.5 text-[10.5px] uppercase tracking-[1px] text-txt-3">
              <span className="w-[200px] shrink-0">
                {t("routing.capability", { defaultValue: "能力" })}
              </span>
              <span className="w-5 text-center">→</span>
              <span className="flex-1">
                {t("routing.provider", { defaultValue: "Provider" })}
              </span>
              <span className="w-[120px] text-right">
                {t("routing.fallbackHeader", { defaultValue: "回退链" })}
              </span>
            </div>

            {Object.entries(editRoutes).map(([cap, prov]) => (
              <div
                key={cap}
                className="flex items-center gap-3 px-3 py-2 bg-bg-0 border border-[var(--line-soft)] rounded-s hover:border-[#2f3647] transition-colors"
              >
                <span className="w-[200px] shrink-0 text-[12px] text-txt-1 font-medium font-mono">
                  <span className="text-txt-2">{cap}</span>
                  <span className="ml-1.5 text-[10.5px] text-txt-3">
                    {CAPABILITY_LABELS[cap] || ""}
                  </span>
                </span>
                <span className="w-5 text-center text-txt-3 font-mono text-[11px]">
                  →
                </span>
                <Select
                  className="flex-1 max-w-[200px] h-7 text-[11px]"
                  value={prov}
                  onChange={(e) => handleRouteChange(cap, e.target.value)}
                >
                  {providerList.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </Select>
                <span className="w-[120px] text-right font-mono text-[10.5px] text-txt-3">
                  {data.fallback?.[cap]?.join(", ") || "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ====== Provider Configs ====== */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* OpenRouter */}
        <Card
          title="OpenRouter"
          subtitle={t("routing.openrouterDesc", {
            defaultValue: "多模型统一网关",
          })}
          actions={
            <Button
              size="sm"
              loading={saveOpenRouter.isPending}
              disabled={!orDirty}
              onClick={() => saveOpenRouter.mutate()}
            >
              {t("common.save")}
            </Button>
          }
        >
          <Field
            label={t("routing.modelLabel", { defaultValue: "默认模型" })}
          >
            <TextInput
              value={orModel}
              placeholder="openai/gpt-image-1"
              onChange={(e) => handleOrFieldChange(setOrModel, e.target.value)}
            />
          </Field>
          <Field label={t("routing.baseUrlLabel", { defaultValue: "API 端点" })}>
            <TextInput
              value={orBaseUrl}
              placeholder="https://openrouter.ai/api/v1"
              onChange={(e) =>
                handleOrFieldChange(setOrBaseUrl, e.target.value)
              }
            />
          </Field>
          <Field label={t("routing.apiKeyLabel", { defaultValue: "API Key" })}>
            <TextInput
              type="password"
              value={orApiKey}
              placeholder={
                openrouterCfg?.api_key_masked ||
                t("routing.apiKeyPlaceholder", {
                  defaultValue: "留空不更新",
                })
              }
              onChange={(e) =>
                handleOrFieldChange(setOrApiKey, e.target.value)
              }
            />
          </Field>
          <div className="flex items-center gap-2 mt-1">
            <Led
              color={
                openrouterCfg?.api_key_configured
                  ? "green"
                  : "red"
              }
              size={7}
            />
            <span className="text-[11px] text-txt-2">
              {openrouterCfg?.api_key_configured
                ? `${
                    openrouterCfg.api_key_masked || ""
                  } — ${t("routing.configured", { defaultValue: "已配置" })}`
                : t("routing.noConfig", { defaultValue: "未配置" })}
            </span>
          </div>
        </Card>

        {/* Seedream */}
        <Card
          title="Seedream"
          subtitle={t("routing.seedreamDesc", {
            defaultValue: "火山方舟 ARK 生图",
          })}
          actions={
            <Button
              size="sm"
              loading={saveSeedream.isPending}
              disabled={!sdDirty}
              onClick={() => saveSeedream.mutate()}
            >
              {t("common.save")}
            </Button>
          }
        >
          <Field
            label={t("routing.modelLabel", { defaultValue: "模型" })}
          >
            <TextInput
              value={sdModel}
              placeholder="doubao-seedream-5-0-260128"
              onChange={(e) => {
                setSdModel(e.target.value);
                setSdDirty(true);
              }}
            />
          </Field>
          <Field label={t("routing.baseUrlLabel", { defaultValue: "API 端点" })}>
            <TextInput
              value={sdBaseUrl}
              placeholder="https://ark.cn-beijing.volces.com/api/v3"
              onChange={(e) => {
                setSdBaseUrl(e.target.value);
                setSdDirty(true);
              }}
            />
          </Field>
          <div className="flex items-center gap-2 mt-1">
            <Led
              color={
                seedreamCfg?.api_key_configured
                  ? "green"
                  : "red"
              }
              size={7}
            />
            <span className="text-[11px] text-txt-2">
              {seedreamCfg?.api_key_configured
                ? t("routing.configured", { defaultValue: "已配置" })
                : t("routing.noConfig", { defaultValue: "未配置" })}
            </span>
          </div>
        </Card>

        {/* Seedance */}
        <Card
          title="Seedance"
          subtitle={t("routing.seedanceDesc", {
            defaultValue: "火山方舟 ARK 生视频",
          })}
          actions={
            <Button
              size="sm"
              loading={saveSeedance.isPending}
              disabled={!sdaDirty}
              onClick={() => saveSeedance.mutate()}
            >
              {t("common.save")}
            </Button>
          }
        >
          <Field
            label={t("routing.modelLabel", { defaultValue: "模型" })}
          >
            <TextInput
              value={sdaModel}
              placeholder="doubao-seedance-1-5-pro-251215"
              onChange={(e) => {
                setSdaModel(e.target.value);
                setSdaDirty(true);
              }}
            />
          </Field>
          <Field label={t("routing.baseUrlLabel", { defaultValue: "API 端点" })}>
            <TextInput
              value={sdaBaseUrl}
              placeholder="https://ark.cn-beijing.volces.com/api/v3"
              onChange={(e) => {
                setSdaBaseUrl(e.target.value);
                setSdaDirty(true);
              }}
            />
          </Field>
          <div className="flex items-center gap-2 mt-1">
            <Led
              color={
                seedanceCfg?.api_key_configured
                  ? "green"
                  : "red"
              }
              size={7}
            />
            <span className="text-[11px] text-txt-2">
              {seedanceCfg?.api_key_configured
                ? t("routing.configured", { defaultValue: "已配置" })
                : t("routing.noConfig", { defaultValue: "未配置" })}
            </span>
          </div>
        </Card>
      </div>

      {/* ====== Registered Providers ====== */}
      <Card
        title={t("routing.providers")}
        subtitle={t("routing.providersDesc", {
          defaultValue: "已注册 Provider 及其支持的能力",
        })}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data?.providers.map((p) => (
            <div
              key={p.name}
              className="px-3 py-3 bg-bg-0 border border-[var(--line-soft)] rounded-s"
            >
              <div className="flex items-center gap-2 mb-2">
                <Led
                  color={
                    configData?.providers?.[p.name]?.api_key_configured
                      ? "green"
                      : "amber"
                  }
                  size={7}
                />
                <span className="text-[13px] font-semibold text-txt-0">
                  {p.name}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {p.capabilities.map((c) => (
                  <span
                    key={c}
                    className="px-1.5 py-0.5 rounded font-mono text-[10px] text-txt-1 bg-bg-3 border border-line"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

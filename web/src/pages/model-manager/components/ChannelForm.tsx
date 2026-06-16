/** 通道编辑表单（创建/编辑弹窗）— 支持 provider-specific 字段 */
import { useState, useEffect } from "react";
import type { Channel } from "../ModelManager";

type Props = {
  channel: Channel | null;
  onSave: (data: Record<string, unknown>) => void;
  onClose: () => void;
};

const PROVIDER_TYPES = [
  { value: "openrouter", label: "OpenRouter", native: true, url: "https://openrouter.ai" },
  { value: "openai", label: "OpenAI", native: true, url: "https://platform.openai.com" },
  { value: "replicate", label: "Replicate", native: true, url: "https://replicate.com" },
  { value: "ollama", label: "Ollama", native: true, url: "https://ollama.com" },
  { value: "custom", label: "自定义", native: false },
];

const PROVIDER_DEFAULTS: Record<string, { base_url: string }> = {
  openrouter: { base_url: "https://openrouter.ai/api/v1" },
  openai: { base_url: "https://api.openai.com/v1" },
  replicate: { base_url: "https://api.replicate.com/v1" },
  ollama: { base_url: "http://localhost:11434" },
  custom: { base_url: "" },
};

export function ChannelForm({ channel, onSave, onClose }: Props) {
  const isEdit = !!channel;

  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [providerType, setProviderType] = useState("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [defaultModel, setDefaultModel] = useState("");

  // OpenRouter 专属字段（存储在 metadata 中）
  const [httpReferer, setHttpReferer] = useState("");
  const [appTitle, setAppTitle] = useState("");

  useEffect(() => {
    if (channel) {
      setName(channel.name);
      setDisplayName(channel.display_name);
      setProviderType(channel.provider_type);
      setBaseUrl(channel.base_url);
      setApiKey("");
      setDefaultModel(channel.default_model);
      // 读取 metadata 中的 OpenRouter 专属字段
      const meta = channel.metadata || {};
      setHttpReferer((meta.http_referer as string) || "");
      setAppTitle((meta.app_title as string) || "");
    }
  }, [channel]);

  const handleSubmit = () => {
    if (!name.trim() || !displayName.trim()) return;

    const metadata: Record<string, unknown> = {};
    if (channel?.metadata) Object.assign(metadata, channel.metadata);

    if (providerType === "openrouter") {
      if (httpReferer.trim()) metadata.http_referer = httpReferer.trim();
      else delete metadata.http_referer;
      if (appTitle.trim()) metadata.app_title = appTitle.trim();
      else delete metadata.app_title;
    }

    const data: Record<string, unknown> = {
      name: name.trim(),
      display_name: displayName.trim(),
      provider_type: providerType,
      base_url: baseUrl.trim(),
      default_model: defaultModel.trim(),
    };
    if (apiKey.trim()) data.api_key = apiKey.trim();
    if (Object.keys(metadata).length > 0) data.metadata = metadata;
    onSave(data);
  };

  const hasNativeSupport = PROVIDER_TYPES.find((p) => p.value === providerType)?.native;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#1a1c1f] border border-gray-700 rounded-xl w-full max-w-lg mx-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-base font-semibold text-white">
            {isEdit ? "编辑通道" : "添加通道"}
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl leading-none">&times;</button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          <div>
            <label className="block text-xs text-gray-400 mb-1">通道标识 *</label>
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
              placeholder="如: my-openrouter" disabled={isEdit} />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">显示名称 *</label>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
              placeholder="如: OpenRouter 主通道" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Provider 类型</label>
            <div className="flex gap-2">
              <select value={providerType} onChange={(e) => {
                const newType = e.target.value;
                setProviderType(newType);
                // 自动填充默认 Base URL
                if (PROVIDER_DEFAULTS[newType]?.base_url !== undefined) {
                  setBaseUrl(PROVIDER_DEFAULTS[newType].base_url);
                }
              }}
                className="flex-1 bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500">
                {PROVIDER_TYPES.map((pt) => (
                  <option key={pt.value} value={pt.value}>
                    {pt.label}{pt.native ? " · 原生支持" : ""}
                  </option>
                ))}
              </select>
              {(() => {
                const provider = PROVIDER_TYPES.find((p) => p.value === providerType);
                if (provider?.url) {
                  return (
                    <a
                      href={provider.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`访问 ${provider.label} 官网`}
                      className="flex items-center justify-center px-3 bg-[#242629] border border-gray-700 rounded-lg text-gray-400 hover:text-blue-400 hover:border-blue-500/50 transition-colors"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                      </svg>
                    </a>
                  );
                }
                return null;
              })()}
            </div>
          </div>

          {/* Provider 专属提示 */}
          {hasNativeSupport && (
            <div className="flex items-center gap-2 px-3 py-2 bg-green-500/10 border border-green-500/30 rounded-lg">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-green-400 flex-shrink-0">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span className="text-xs text-green-400">此 Provider 支持原生 SDK 集成，可提供更精准的连接测试</span>
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-400 mb-1">Base URL</label>
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500 font-mono"
              placeholder="如: https://api.openai.com/v1" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              API Key {isEdit ? "(留空则不修改)" : ""}
            </label>
            <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500 font-mono"
              type="password"
              placeholder={isEdit ? "留空保持不变" : "输入 API Key"} />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">默认模型</label>
            <input value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
              placeholder="如: gpt-4o" />
          </div>

          {/* OpenRouter 专属字段 */}
          {providerType === "openrouter" && (
            <>
              <div className="pt-2 border-t border-gray-800">
                <label className="block text-xs text-gray-300 mb-2 flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-green-400"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                  OpenRouter 专属配置
                </label>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">HTTP Referer（可选）</label>
                <input value={httpReferer} onChange={(e) => setHttpReferer(e.target.value)}
                  className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500 font-mono"
                  placeholder="如: https://spriteflow.app" />
                <p className="text-[11px] text-gray-600 mt-1">用于 OpenRouter 排行榜统计</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">应用名称（可选）</label>
                <input value={appTitle} onChange={(e) => setAppTitle(e.target.value)}
                  className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
                  placeholder="如: SpriteFlow" />
                <p className="text-[11px] text-gray-600 mt-1">用于 OpenRouter 排行榜展示</p>
              </div>
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-gray-800">
          <button onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
          <button onClick={handleSubmit}
            className="px-4 py-2 text-sm bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors disabled:opacity-50"
            disabled={!name.trim() || !displayName.trim()}>
            {isEdit ? "保存" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** 通道列表 */
import type { Channel } from "../ModelManager";
import { useConfirm } from "@/components/ui/Confirm";

type Props = {
  channels: Channel[];
  onAdd: () => void;
  onEdit: (ch: Channel) => void;
  onDelete: (id: string) => void;
  onTest: (id: string) => void;
};

const PROVIDER_LABELS: Record<string, string> = {
  openrouter: "OpenRouter",
  seedream: "Seedream (火山方舟)",
  seedance: "Seedance (火山方舟)",
  rembg: "Rembg (本地)",
  volcengine_image: "火山引擎图像",
  openai: "OpenAI",
  replicate: "Replicate",
  ollama: "Ollama",
};

/** 有原生 SDK 支持的 provider */
const NATIVE_PROVIDERS = new Set(["openai", "openrouter", "replicate", "ollama"]);

export function ChannelList({ channels, onAdd, onEdit, onDelete, onTest }: Props) {
  const confirm = useConfirm();

  const handleDelete = async (ch: Channel) => {
    const ok = await confirm({
      title: "删除通道",
      message: `确定删除通道 "${ch.display_name}" 吗？删除后关联的路由也将被移除，此操作不可撤销。`,
      okText: "删除",
      cancelText: "取消",
      variant: "danger",
    });
    if (ok) onDelete(ch.id);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">通道列表</h2>
        <button
          onClick={onAdd}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
          添加通道
        </button>
      </div>

      {channels.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <div className="flex justify-center mb-3">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-gray-600">
              <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
              <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
              <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
              <circle cx="12" cy="20" r="1"/>
            </svg>
          </div>
          <p className="text-sm">暂无通道配置</p>
          <p className="text-xs mt-1 text-gray-600">点击上方按钮添加第一个通道</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {channels.map((ch) => (
            <div
              key={ch.id}
              className="flex items-center justify-between bg-[#1a1c1f] border border-gray-800 rounded-lg px-4 py-3 hover:border-gray-600 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                  ch.status === "active" ? "bg-green-400" : "bg-gray-500"
                }`} title={ch.status === "active" ? "在线" : "离线"} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white truncate">{ch.display_name}</span>
                    <span className="text-[11px] text-gray-500 bg-[#2a2d31] px-1.5 py-0.5 rounded">
                      {PROVIDER_LABELS[ch.provider_type] || ch.provider_type}
                    </span>
                    {NATIVE_PROVIDERS.has(ch.provider_type) && (
                      <span className="text-[10px] text-green-400 bg-green-400/10 px-1.5 py-0.5 rounded">
                        原生SDK
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5 truncate">
                    {ch.base_url || "未配置 Base URL"} · {ch.default_model || "无默认模型"} · {ch.route_count} 个路由
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0 ml-3">
                <button
                  onClick={() => onTest(ch.id)}
                  className="px-2.5 py-1 text-xs text-gray-400 hover:text-green-400 hover:bg-[#2a2d31] rounded transition-colors"
                  title="测试连接"
                >
                  测试
                </button>
                <button
                  onClick={() => onEdit(ch)}
                  className="px-2.5 py-1 text-xs text-gray-400 hover:text-blue-400 hover:bg-[#2a2d31] rounded transition-colors"
                >
                  编辑
                </button>
                <button
                  onClick={() => handleDelete(ch)}
                  className="px-2.5 py-1 text-xs text-gray-400 hover:text-red-400 hover:bg-[#2a2d31] rounded transition-colors"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

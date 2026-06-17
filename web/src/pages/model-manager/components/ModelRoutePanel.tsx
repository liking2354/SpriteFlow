/** 模型路由列表面板 — 支持分页 + 行内路由增删改 + 删除模型 */
import { useState } from "react";
import type { ModelEntry, Channel, RouteItem } from "../ModelManager";
import { useConfirm } from "@/components/ui/Confirm";

type Props = {
  models: ModelEntry[];
  loading: boolean;
  search: string;
  onSearchChange: (v: string) => void;
  category: string;
  onCategoryChange: (v: string) => void;
  categories: string[];
  channels: Channel[];
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (p: number) => void;
  onAddRoute: (modelId: string, route: RouteInput) => Promise<void>;
  onUpdateRoute: (modelId: string, routeId: string, data: Record<string, unknown>) => Promise<void>;
  onDeleteRoute: (modelId: string, routeId: string) => Promise<void>;
  onDeleteModel: (modelId: string) => void;
  onEditModel: (model: ModelEntry) => void;
  defaults: Record<string, string>;
  onSetDefault: (category: string, modelId: string, subcategory?: string) => Promise<void>;
};

type RouteInput = { channel_id: string; priority: number; model_override: string; param_overrides: Record<string, unknown>; status: string };

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  text: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 7 4 4 20 4 20 7" />
      <line x1="9" y1="20" x2="15" y2="20" />
      <line x1="12" y1="4" x2="12" y2="20" />
    </svg>
  ),
  image: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  ),
  video: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="23 7 16 12 23 17 23 7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  ),
  audio: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18V5l12-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="16" r="3" />
    </svg>
  ),
  utility: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
};

/** 单模型路由行组件 */
function RouteRow({
  route,
  channels,
  modelId,
  onUpdate,
  onDelete,
}: {
  route: RouteItem;
  channels: Channel[];
  modelId: string;
  onUpdate: (modelId: string, routeId: string, data: Record<string, unknown>) => Promise<void>;
  onDelete: (modelId: string, routeId: string) => Promise<void>;
}) {
  const ch = channels.find((c) => c.id === route.channel_id);
  const [editing, setEditing] = useState(false);
  const [override, setOverride] = useState(route.model_override);
  const [prio, setPrio] = useState(route.priority);

  const handleSave = () => {
    onUpdate(modelId, route.id, { model_override: override, priority: prio });
    setEditing(false);
  };

  const handleToggle = () => {
    onUpdate(modelId, route.id, { status: route.status === "active" ? "inactive" : "active" });
  };

  if (editing) {
    return (
      <div className="flex items-center gap-2 py-1.5 pl-8 pr-3">
        <span className="text-[11px] text-gray-500 w-8 flex-shrink-0">#{route.priority}</span>
        <span className="text-xs text-gray-300 flex-shrink-0 w-24 truncate">{ch?.display_name || route.channel_id}</span>
        <input value={prio} onChange={(e) => setPrio(Number(e.target.value))} type="number" min={0}
          className="w-14 bg-[#1a1c1f] border border-blue-500 rounded px-1.5 py-0.5 text-xs text-white outline-none" />
        <input value={override} onChange={(e) => setOverride(e.target.value)} placeholder="模型覆盖"
          className="flex-1 bg-[#1a1c1f] border border-blue-500 rounded px-2 py-0.5 text-xs text-white outline-none" />
        <button onClick={handleSave} className="text-xs text-green-400 hover:bg-green-400/10 px-2 py-0.5 rounded">保存</button>
        <button onClick={() => setEditing(false)} className="text-xs text-gray-400 hover:text-white px-2 py-0.5 rounded">取消</button>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 py-1.5 pl-8 pr-3 ${route.status !== "active" ? "opacity-40" : ""}`}>
      <span className="text-[10px] text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded font-mono flex-shrink-0 w-8 text-center">
        #{route.priority}
      </span>
      <span className="text-xs text-gray-300 flex-shrink-0 w-24 truncate">{ch?.display_name || route.channel_id}</span>
      {route.model_override ? (
        <code className="text-[10px] text-yellow-400 bg-yellow-400/10 px-1.5 py-0.5 rounded flex-shrink-0 truncate max-w-[120px]">{route.model_override}</code>
      ) : (
        <span className="flex-1" />
      )}
      <div className="flex items-center gap-0.5">
        <button onClick={handleToggle} className="text-[10px] text-gray-500 hover:text-yellow-400 px-1.5 py-0.5 rounded hover:bg-[#2a2d31]"
          title={route.status === "active" ? "停用" : "启用"}>
          {route.status === "active" ? "停用" : "启用"}
        </button>
        <button onClick={() => setEditing(true)} className="text-[10px] text-gray-500 hover:text-blue-400 px-1.5 py-0.5 rounded hover:bg-[#2a2d31]">编辑</button>
        <button onClick={() => onDelete(modelId, route.id)} className="text-[10px] text-gray-500 hover:text-red-400 px-1.5 py-0.5 rounded hover:bg-[#2a2d31]">删除</button>
      </div>
    </div>
  );
}

export function ModelRoutePanel({
  models, loading, search, onSearchChange,
  category, onCategoryChange, categories, channels,
  page, totalPages, total, onPageChange,
  onAddRoute, onUpdateRoute, onDeleteRoute, onDeleteModel, onEditModel,
  defaults, onSetDefault,
}: Props) {
  const confirm = useConfirm();
  const [expandedModels, setExpandedModels] = useState<Set<string>>(new Set());
  const [addRouteModel, setAddRouteModel] = useState<string | null>(null);
  const [newRouteChannel, setNewRouteChannel] = useState("");

  const toggleExpand = (modelId: string) => {
    setExpandedModels(prev => {
      const next = new Set(prev);
      if (next.has(modelId)) next.delete(modelId);
      else next.add(modelId);
      return next;
    });
  };

  const handleQuickAdd = (modelId: string) => {
    if (!newRouteChannel) return;
    onAddRoute(modelId, {
      channel_id: newRouteChannel,
      priority: 0,
      model_override: "",
      param_overrides: {},
      status: "active",
    });
    setAddRouteModel(null);
    setNewRouteChannel("");
  };

  const availableChannels = channels.filter((c) => c.status === "active");

  return (
    <div className="flex flex-col h-full">
      {/* 搜索与筛选 */}
      <div className="flex items-center gap-3 mb-4 flex-shrink-0">
        <div className="relative flex-1 max-w-xs">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></svg>
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索模型..."
            className="w-full bg-[#242629] border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white outline-none focus:border-blue-500"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onCategoryChange("")}
            className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
              !category ? "bg-blue-500/20 text-blue-400 border border-blue-500/40" : "text-gray-400 hover:text-gray-200 border border-transparent"
            }`}
          >全部</button>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => onCategoryChange(category === cat ? "" : cat)}
              className={`px-2.5 py-1 text-xs rounded-full transition-colors ${
                category === cat ? "bg-blue-500/20 text-blue-400 border border-blue-500/40" : "text-gray-400 hover:text-gray-200 border border-transparent"
              }`}
            ><span className="inline mr-1 align-middle">{CATEGORY_ICONS[cat]}</span>{cat}</button>
          ))}
        </div>
        <div className="text-xs text-gray-500 ml-auto">共 {total} 个模型</div>
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-500">
            <div className="w-5 h-5 border-2 border-t-transparent border-gray-400 rounded-full animate-spin mr-2" />
            加载中...
          </div>
        ) : models.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <div className="flex justify-center mb-3">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-gray-600">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                <line x1="12" y1="22.08" x2="12" y2="12"/>
              </svg>
            </div>
            <p className="text-sm">暂无匹配的模型</p>
          </div>
        ) : (
          <div className="space-y-2">
            {models.map((m) => {
              const isExpanded = expandedModels.has(m.model_id);
              const sortedRoutes = [...m.routes].sort((a, b) => a.priority - b.priority);
              const modelChannels = new Set(m.routes.map((r) => r.channel_id));
              const addableChannels = availableChannels.filter((c) => !modelChannels.has(c.id));

              return (
                <div key={m.model_id} className="bg-[#1a1c1f] border border-gray-800 rounded-lg overflow-hidden hover:border-gray-600 transition-colors">
                  {/* 模型头部 */}
                  <div className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="flex items-center text-gray-400">{CATEGORY_ICONS[m.category] || (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 2l9 4.5v11L12 22l-9-4.5v-11z"/>
                          <path d="M12 22V12"/>
                          <path d="M12 12l9-4.5"/>
                          <path d="M12 12L3 7.5"/>
                        </svg>
                      )}</span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white truncate">{m.name}</span>
                          {m.is_default && (
                            <span className="flex-shrink-0 text-[10px] text-amber-400 bg-amber-400/10 border border-amber-400/30 px-1.5 py-0.5 rounded-full" title="默认模型">
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" className="inline mr-0.5 -mt-0.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                              默认
                            </span>
                          )}
                          <code className="text-[11px] text-gray-500 bg-[#2a2d31] px-1.5 py-0.5 rounded font-mono">{m.model_id}</code>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[11px] text-gray-500 bg-[#2a2d31] px-1.5 py-0.5 rounded">{m.category}</span>
                          {m.subcategory && (
                            <span className="text-[11px] text-purple-400 bg-purple-400/10 border border-purple-400/20 px-1.5 py-0.5 rounded">{m.subcategory === "generation" ? "生成" : m.subcategory === "editing" ? "编辑" : m.subcategory}</span>
                          )}
                          <span className="text-[11px] text-gray-600">{m.service}</span>
                          {m.routes.length > 0 && (
                            <span className="text-[10px] text-blue-400">{m.routes.filter(r => r.status === "active").length}/{m.routes.length} 个路由</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0 ml-3">
                      {!m.is_default && (
                        <button
                          onClick={() => onSetDefault(m.category, m.model_id, m.subcategory || "")}
                          className="px-2.5 py-1 text-xs text-gray-500 hover:text-amber-400 hover:bg-amber-400/10 rounded transition-colors"
                          title={`设为 ${m.category}${m.subcategory ? ` (${m.subcategory})` : ""} 默认模型`}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline mr-0.5 -mt-0.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                          设为默认
                        </button>
                      )}
                      <button
                        onClick={() => toggleExpand(m.model_id)}
                        className="px-2.5 py-1 text-xs text-gray-400 hover:text-white hover:bg-[#242629] rounded transition-colors"
                      >
                        {isExpanded ? "收起" : `展开 (${m.routes.length})`}
                      </button>
                      <button
                        onClick={() => onEditModel(m)}
                        className="px-2.5 py-1 text-xs text-gray-500 hover:text-blue-400 hover:bg-blue-400/10 rounded transition-colors"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => {
                          confirm({
                            title: "删除模型",
                            message: `确定要删除模型「${m.name}」吗？删除后将从工作流节点列表中移除，且不可恢复。`,
                            variant: "danger",
                          }).then((ok) => { if (ok) onDeleteModel(m.model_id); });
                        }}
                        className="px-2.5 py-1 text-xs text-gray-500 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
                      >
                        删除
                      </button>
                    </div>
                  </div>

                  {/* 展开的路由列表 */}
                  {isExpanded && (
                    <div className="border-t border-gray-800 bg-[#151618]">
                      {sortedRoutes.length === 0 ? (
                        <div className="px-8 py-4 text-xs text-gray-500">暂无路由配置</div>
                      ) : (
                        <div className="py-1">
                          {sortedRoutes.map((r) => (
                            <RouteRow
                              key={r.id}
                              route={r}
                              channels={channels}
                              modelId={m.model_id}
                              onUpdate={onUpdateRoute}
                              onDelete={onDeleteRoute}
                            />
                          ))}
                        </div>
                      )}

                      {/* 快速添加路由 */}
                      {addRouteModel === m.model_id ? (
                        <div className="flex items-center gap-2 px-8 py-2 border-t border-gray-800">
                          <select
                            value={newRouteChannel}
                            onChange={(e) => setNewRouteChannel(e.target.value)}
                            className="flex-1 bg-[#1a1c1f] border border-gray-700 rounded px-2 py-1 text-xs text-white outline-none focus:border-blue-500"
                          >
                            <option value="">选择通道...</option>
                            {addableChannels.map((c) => (
                              <option key={c.id} value={c.id}>{c.display_name}</option>
                            ))}
                          </select>
                          <button onClick={() => handleQuickAdd(m.model_id)}
                            disabled={!newRouteChannel}
                            className="text-xs text-green-400 hover:bg-green-400/10 px-2 py-1 rounded disabled:opacity-30">
                            添加
                          </button>
                          <button onClick={() => { setAddRouteModel(null); setNewRouteChannel(""); }}
                            className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded">取消</button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setAddRouteModel(m.model_id)}
                          className="w-full flex items-center justify-center gap-1 py-2 text-xs text-gray-500 hover:text-blue-400 hover:bg-[#1a1c1f] border-t border-gray-800 transition-colors"
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M12 5v14M5 12h14"/></svg>
                          添加路由
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 分页 */}
      {total > 0 && (
        <div className="flex items-center justify-between pt-4 mt-auto border-t border-gray-800 flex-shrink-0">
          <span className="text-xs text-gray-500">
            第 {page + 1}/{totalPages} 页 · 共 {total} 个模型
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange(0)}
              disabled={page === 0}
              className="px-2 py-1 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed rounded hover:bg-[#242629]"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/></svg>
            </button>
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page === 0}
              className="px-2 py-1 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed rounded hover:bg-[#242629]"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum: number;
              if (totalPages <= 5) {
                pageNum = i;
              } else if (page < 3) {
                pageNum = i;
              } else if (page > totalPages - 3) {
                pageNum = totalPages - 5 + i;
              } else {
                pageNum = page - 2 + i;
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => onPageChange(pageNum)}
                  className={`w-7 h-7 text-xs rounded transition-colors ${
                    pageNum === page ? "bg-blue-500 text-white" : "text-gray-400 hover:text-white hover:bg-[#242629]"
                  }`}
                >{pageNum + 1}</button>
              );
            })}
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed rounded hover:bg-[#242629]"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
            <button
              onClick={() => onPageChange(totalPages - 1)}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 text-xs text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed rounded hover:bg-[#242629]"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/></svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

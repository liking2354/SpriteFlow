/** 模型路由编辑器 — 基于单条 CRUD 的差异保存 */
import { useState, useEffect } from "react";
import type { ModelEntry, Channel, RouteItem } from "../ModelManager";

type RouteInput = Omit<RouteItem, "id" | "model_id" | "channel_name" | "channel_display_name" | "created_at" | "updated_at">;

type TrackedRoute = RouteInput & { routeId?: string };

export type RouteDiff = {
  toAdd: RouteInput[];
  toUpdate: { routeId: string; changes: Record<string, unknown> }[];
  toRemove: string[];
};

type Props = {
  model: ModelEntry;
  channels: Channel[];
  onSave: (modelId: string, diff: RouteDiff) => void;
  onClose: () => void;
};

export function RouteEditor({ model, channels, onSave, onClose }: Props) {
  const activeChannels = channels.filter((c) => c.status === "active");

  const [initialRoutes, setInitialRoutes] = useState<Map<string, TrackedRoute>>(new Map());
  const [routes, setRoutes] = useState<Map<string, TrackedRoute>>(new Map());
  const [dragIdx, setDragIdx] = useState<number | null>(null);

  useEffect(() => {
    const m = new Map<string, TrackedRoute>();
    for (const r of model.routes) {
      m.set(r.channel_id, {
        routeId: r.id,
        channel_id: r.channel_id,
        priority: r.priority,
        model_override: r.model_override,
        param_overrides: r.param_overrides,
        status: r.status,
      });
    }
    setInitialRoutes(new Map(m));
    setRoutes(new Map(m));
  }, [model]);

  const sorted = [...routes.values()]
    .filter((r) => r.status === "active")
    .sort((a, b) => a.priority - b.priority);

  const availableChannels = activeChannels.filter((c) => !routes.has(c.id));

  const addRoute = (channelId: string) => {
    setRoutes(prev => {
      const next = new Map(prev);
      const maxP = [...next.values()].reduce((max, r) => Math.max(max, r.priority), -1);
      next.set(channelId, {
        channel_id: channelId,
        priority: maxP + 1,
        model_override: "",
        param_overrides: {},
        status: "active",
      });
      return next;
    });
  };

  const removeRoute = (channelId: string) => {
    setRoutes(prev => {
      const next = new Map(prev);
      next.delete(channelId);
      return next;
    });
  };

  const toggleStatus = (channelId: string) => {
    setRoutes(prev => {
      const next = new Map(prev);
      const r = next.get(channelId);
      if (r) {
        r.status = r.status === "active" ? "inactive" : "active";
        next.set(channelId, { ...r });
      }
      return next;
    });
  };

  const updateRoute = (channelId: string, field: string, value: string) => {
    setRoutes(prev => {
      const next = new Map(prev);
      const r = next.get(channelId);
      if (r) {
        next.set(channelId, { ...r, [field]: value });
      }
      return next;
    });
  };

  // 拖拽排序
  const handleDragStart = (idx: number) => setDragIdx(idx);
  const handleDragOver = (idx: number) => {
    if (dragIdx === null || dragIdx === idx) return;
    const newRoutes = new Map(routes);
    const active = [...newRoutes.values()]
      .filter((r) => r.status === "active")
      .sort((a, b) => a.priority - b.priority);
    const [moved] = active.splice(dragIdx, 1);
    active.splice(idx, 0, moved);
    active.forEach((r, i) => {
      newRoutes.set(r.channel_id, { ...r, priority: i });
    });
    setRoutes(newRoutes);
    setDragIdx(idx);
  };
  const handleDragEnd = () => setDragIdx(null);

  const handleSave = () => {
    const toAdd: RouteInput[] = [];
    const toUpdate: { routeId: string; changes: Record<string, unknown> }[] = [];
    const toRemove: string[] = [];

    // 1. 找出删除的：在 initial 但不在当前
    for (const [chId, initial] of initialRoutes) {
      if (!routes.has(chId) && initial.routeId) {
        toRemove.push(initial.routeId);
      }
    }

    // 2. 找出新增 + 修改的
    for (const [chId, current] of routes) {
      const initial = initialRoutes.get(chId);
      if (!initial) {
        // 新增
        toAdd.push({
          channel_id: current.channel_id,
          priority: current.priority,
          model_override: current.model_override,
          param_overrides: current.param_overrides,
          status: current.status,
        });
      } else if (current.routeId) {
        // 已有路由 → 检查变更
        const changes: Record<string, unknown> = {};
        if (current.priority !== initial.priority) changes.priority = current.priority;
        if (current.model_override !== initial.model_override) changes.model_override = current.model_override;
        if (current.status !== initial.status) changes.status = current.status;
        if (JSON.stringify(current.param_overrides) !== JSON.stringify(initial.param_overrides))
          changes.param_overrides = current.param_overrides;
        if (Object.keys(changes).length > 0) {
          toUpdate.push({ routeId: current.routeId, changes });
        }
      }
    }

    onSave(model.model_id, { toAdd, toUpdate, toRemove });
  };

  const nothingChanged = (
    (() => {
      let add = 0, upd = 0, rem = 0;
      for (const [chId] of initialRoutes) { if (!routes.has(chId)) rem++; }
      for (const [chId, current] of routes) {
        const initial = initialRoutes.get(chId);
        if (!initial) { add++; continue; }
        if (current.priority !== initial.priority || current.model_override !== initial.model_override ||
            current.status !== initial.status || JSON.stringify(current.param_overrides) !== JSON.stringify(initial.param_overrides)) {
          upd++;
        }
      }
      return add + upd + rem === 0;
    })()
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#1a1c1f] border border-gray-700 rounded-xl w-full max-w-xl mx-4 shadow-2xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 flex-shrink-0">
          <div>
            <h3 className="text-base font-semibold text-white">{model.name}</h3>
            <p className="text-xs text-gray-500 mt-0.5">{model.category} · {model.model_id}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl leading-none">&times;</button>
        </div>

        <div className="flex-1 overflow-auto p-5 space-y-4">
          {/* 已配置路由 */}
          {sorted.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">路由优先级（拖拽排序）</label>
              <div className="space-y-1.5">
                {sorted.map((r, idx) => {
                  const ch = channels.find((c) => c.id === r.channel_id);
                  return (
                    <div
                      key={r.channel_id}
                      draggable
                      onDragStart={() => handleDragStart(idx)}
                      onDragOver={(e) => { e.preventDefault(); handleDragOver(idx); }}
                      onDragEnd={handleDragEnd}
                      className={`flex items-center gap-3 bg-[#242629] border rounded-lg px-3 py-2.5 cursor-grab active:cursor-grabbing transition-colors ${
                        dragIdx === idx ? "border-blue-500 ring-1 ring-blue-500/30" : "border-gray-700"
                      }`}
                    >
                      <div className="text-gray-500 cursor-grab">
                        <svg width="12" height="16" viewBox="0 0 12 24" fill="currentColor"><circle cx="4" cy="4" r="2"/><circle cx="8" cy="4" r="2"/><circle cx="4" cy="12" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="4" cy="20" r="2"/><circle cx="8" cy="20" r="2"/></svg>
                      </div>
                      <span className="text-[11px] text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded font-mono flex-shrink-0">#{r.priority}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{ch?.display_name || r.channel_id}</div>
                      </div>
                      <input
                        value={r.model_override}
                        onChange={(e) => updateRoute(r.channel_id, "model_override", e.target.value)}
                        placeholder="模型名覆盖"
                        className="w-32 bg-[#1a1c1f] border border-gray-700 rounded px-2 py-1 text-xs text-white outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => removeRoute(r.channel_id)}
                        className="text-gray-500 hover:text-red-400 text-sm px-1">✕</button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 已停用路由 */}
          {[...routes.values()].filter((r) => r.status !== "active").length > 0 && (
            <div>
              <label className="block text-xs text-gray-500 mb-2">已停用</label>
              <div className="space-y-1">
                {[...routes.values()].filter((r) => r.status !== "active").map((r) => {
                  const ch = channels.find((c) => c.id === r.channel_id);
                  return (
                    <div key={r.channel_id}
                      className="flex items-center gap-3 bg-[#242629] border border-gray-800 rounded-lg px-3 py-2 opacity-50">
                      <span className="text-xs text-gray-500 line-through truncate flex-1">{ch?.display_name || r.channel_id}</span>
                      <button onClick={() => toggleStatus(r.channel_id)}
                        className="text-xs text-gray-500 hover:text-green-400">启用</button>
                      <button onClick={() => removeRoute(r.channel_id)}
                        className="text-xs text-gray-500 hover:text-red-400">移除</button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 添加通道路由 */}
          {availableChannels.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-2">添加通道</label>
              <div className="flex flex-wrap gap-1.5">
                {availableChannels.map((ch) => (
                  <button
                    key={ch.id}
                    onClick={() => addRoute(ch.id)}
                    className="flex items-center gap-1 px-2.5 py-1 text-xs bg-[#242629] border border-gray-700 rounded-lg text-gray-400 hover:text-blue-400 hover:border-blue-500/40 transition-colors"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M12 5v14M5 12h14"/></svg>
                    {ch.display_name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {routes.size === 0 && availableChannels.length === 0 && (
            <div className="text-center py-8 text-gray-500 text-sm">
              暂无可用通道，请先在"通道管理"中添加通道
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-5 py-4 border-t border-gray-800 flex-shrink-0">
          <span className="text-[11px] text-gray-500">
            新增 {(() => { let c = 0; for (const [chId] of routes) { if (!initialRoutes.has(chId)) c++; } return c; })()} ·
            修改 {(() => { let c = 0; for (const [chId, r] of routes) { const i = initialRoutes.get(chId); if (i && (r.priority !== i.priority || r.model_override !== i.model_override || r.status !== i.status)) c++; } return c; })()} ·
            删除 {(() => { let c = 0; for (const [chId] of initialRoutes) { if (!routes.has(chId)) c++; } return c; })()}
          </span>
          <div className="flex gap-2">
            <button onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
            <button onClick={handleSave}
              disabled={nothingChanged}
              className="px-4 py-2 text-sm bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
              保存路由
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

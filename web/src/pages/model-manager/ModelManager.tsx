/** 模型管理器 — 通道配置 + 模型路由管理 */
import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import toast, { Toaster } from "react-hot-toast";
import axios from "axios";
import { ChannelList } from "./components/ChannelList";
import { ChannelForm } from "./components/ChannelForm";
import { ModelRoutePanel } from "./components/ModelRoutePanel";
import { ModelForm } from "./components/ModelForm";

export type Channel = {
  id: string;
  name: string;
  display_name: string;
  provider_type: string;
  base_url: string;
  default_model: string;
  status: string;
  metadata: Record<string, unknown>;
  route_count: number;
  created_at: string;
  updated_at: string;
};

export type RouteItem = {
  id: string;
  model_id: string;
  channel_id: string;
  channel_name: string;
  channel_display_name: string;
  priority: number;
  model_override: string;
  param_overrides: Record<string, unknown>;
  status: string;
};

export type ModelEntry = {
  model_id: string;
  name: string;
  category: string;
  subcategory: string;
  service: string;
  routes: RouteItem[];
  is_default: boolean;
};

type Tab = "channels" | "models";

export function ModelManager() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("channels");

  const [channels, setChannels] = useState<Channel[]>([]);
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  // 分页
  const pageSize = 20;
  const [page, setPage] = useState(0);
  const [totalModels, setTotalModels] = useState(0);
  const totalPages = Math.max(1, Math.ceil(totalModels / pageSize));

  // Channel form state
  const [channelFormOpen, setChannelFormOpen] = useState(false);
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null);

  // Model form state（新增/编辑自定义模型）
  const [modelFormOpen, setModelFormOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<ModelEntry | null>(null);

  const categories = ["text", "image", "video", "audio", "utility"];

  // ── 数据加载 ──
  const loadDefaults = useCallback(async () => {
    try {
      const res = await axios.get("/api/model-manager/defaults");
      setDefaults(res.data.defaults || {});
    } catch {
      // 静默失败
    }
  }, []);

  const loadChannels = useCallback(async () => {
    try {
      const res = await axios.get("/api/model-manager/channels");
      setChannels(res.data.items);
    } catch {
      toast.error("加载通道列表失败");
    }
  }, []);

  const loadModels = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (categoryFilter) params.set("category", categoryFilter);
      params.set("offset", String(page * pageSize));
      params.set("limit", String(pageSize));
      const res = await axios.get(`/api/model-manager/models?${params}`);
      setModels(res.data.items);
      setTotalModels(res.data.total);
    } catch {
      toast.error("加载模型列表失败");
    } finally {
      setLoading(false);
    }
  }, [search, categoryFilter, page, pageSize]);

  // 搜索或分类变化时重置到第 0 页
  const handleSearchChange = (v: string) => { setSearch(v); setPage(0); };
  const handleCategoryChange = (v: string) => { setCategoryFilter(v); setPage(0); };

  useEffect(() => {
    loadChannels();
    loadDefaults();
  }, [loadChannels, loadDefaults]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  // ── 通道操作 ──
  const handleSaveChannel = async (data: Record<string, unknown>) => {
    try {
      if (editingChannel) {
        await axios.put(`/api/model-manager/channels/${editingChannel.id}`, data);
        toast.success("通道已更新");
      } else {
        await axios.post("/api/model-manager/channels", data);
        toast.success("通道已创建");
      }
      setChannelFormOpen(false);
      setEditingChannel(null);
      loadChannels();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "操作失败";
      toast.error(String(msg));
    }
  };

  const handleDeleteChannel = async (id: string) => {
    try {
      await axios.delete(`/api/model-manager/channels/${id}`);
      toast.success("通道已删除");
      loadChannels();
      loadModels();
    } catch {
      toast.error("删除失败");
    }
  };

  const handleTestChannel = async (id: string) => {
    try {
      const res = await axios.post(`/api/model-manager/channels/${id}/test`);
      if (res.data.success) {
        toast.success(`${res.data.message} (${res.data.latency_ms}ms)`);
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error("测试请求失败");
    }
  };

  // ── 路由操作 ──
  const handleAddRoute = async (modelId: string, route: { channel_id: string; priority: number; model_override: string; param_overrides: Record<string, unknown>; status: string }) => {
    try {
      await axios.post(`/api/model-manager/models/${encodeURIComponent(modelId)}/routes`, route);
      toast.success("路由已添加");
      loadModels();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "添加失败";
      toast.error(String(msg));
    }
  };

  const handleUpdateRoute = async (modelId: string, routeId: string, data: Record<string, unknown>) => {
    try {
      await axios.patch(`/api/model-manager/models/${encodeURIComponent(modelId)}/routes/${routeId}`, data);
      loadModels();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "更新失败";
      toast.error(String(msg));
    }
  };

  const handleDeleteRoute = async (modelId: string, routeId: string) => {
    try {
      await axios.delete(`/api/model-manager/models/${encodeURIComponent(modelId)}/routes/${routeId}`);
      toast.success("路由已删除");
      loadModels();
    } catch {
      toast.error("删除失败");
    }
  };

  // ── 删除模型 ──
  const handleDeleteModel = async (modelId: string) => {
    try {
      // 不含 / 的 model_id 走路径参数，含 / 的走 body 参数
      if (modelId.includes("/")) {
        await axios.delete("/api/workflow/models/nodes", { data: { model_id: modelId } });
      } else {
        await axios.delete(`/api/workflow/models/nodes/${encodeURIComponent(modelId)}`);
      }
      toast.success("模型已删除");
      loadModels();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "删除失败";
      toast.error(String(msg));
    }
  };

  // ── 设置默认模型 ──
  const handleSetDefault = async (category: string, modelId: string, subcategory: string = "") => {
    try {
      const params = subcategory ? `?subcategory=${encodeURIComponent(subcategory)}` : "";
      const res = await axios.put(`/api/model-manager/defaults/${category}${params}`, { model_id: modelId });
      setDefaults(res.data.defaults || {});
      toast.success("默认模型已更新");
      loadModels(); // 刷新列表以更新 is_default 标记
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "设置失败";
      toast.error(String(msg));
    }
  };

  // ── 新增模型 ──
  const handleSaveModel = async (data: Record<string, unknown>) => {
    try {
      await axios.post("/api/workflow/models/nodes", {
        model_id: data.model_id,
        category: data.category,
        subcategory: data.subcategory || "",
        name: data.name,
        service: data.service,
      });
      toast.success("模型已添加");
      setModelFormOpen(false);
      setEditingModel(null);
      loadModels();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "添加失败";
      toast.error(String(msg));
    }
  };

  // ── 编辑模型 ──
  const handleOpenAdd = () => { setEditingModel(null); setModelFormOpen(true); };
  const handleOpenEdit = (model: ModelEntry) => { setEditingModel(model); setModelFormOpen(true); };

  const handleUpdateModel = async (data: Record<string, unknown>) => {
    try {
      await axios.put("/api/workflow/models/nodes/schema", {
        model_id: data.model_id,
        name: data.name,
        category: data.category,
        subcategory: data.subcategory || "",
        service: data.service,
      });
      toast.success("模型已更新");
      setModelFormOpen(false);
      setEditingModel(null);
      loadModels();
    } catch (err: unknown) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail : "更新失败";
      toast.error(String(msg));
    }
  };

  const goToPage = (p: number) => {
    setPage(p);
  };

  return (
    <div className="h-full flex flex-col bg-[#0f1012] text-white">
      {/* 顶部 Tab 导航 */}
      <div className="flex items-center border-b border-gray-800 px-6">
        <button
          onClick={() => setTab("channels")}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            tab === "channels"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline mr-1.5 -mt-0.5"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
          {t("modelManager.channels", "通道管理")}
        </button>
        <button
          onClick={() => setTab("models")}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            tab === "models"
              ? "border-blue-500 text-blue-400"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline mr-1.5 -mt-0.5"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>
          {t("modelManager.models", "模型路由")}
        </button>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-auto p-6">
        {tab === "channels" ? (
          <ChannelList
            channels={channels}
            onAdd={() => { setEditingChannel(null); setChannelFormOpen(true); }}
            onEdit={(ch) => { setEditingChannel(ch); setChannelFormOpen(true); }}
            onDelete={handleDeleteChannel}
            onTest={handleTestChannel}
          />
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">模型路由</h2>
              <button
                onClick={handleOpenAdd}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-sm rounded-lg transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
                新增模型
              </button>
            </div>
            <ModelRoutePanel
              models={models}
              loading={loading}
              search={search}
              onSearchChange={handleSearchChange}
              category={categoryFilter}
              onCategoryChange={handleCategoryChange}
              categories={categories}
              channels={channels}
              page={page}
              totalPages={totalPages}
              total={totalModels}
              onPageChange={goToPage}
              onAddRoute={handleAddRoute}
              onUpdateRoute={handleUpdateRoute}
              onDeleteRoute={handleDeleteRoute}
              onDeleteModel={handleDeleteModel}
              onEditModel={handleOpenEdit}
              defaults={defaults}
              onSetDefault={handleSetDefault}
            />
          </>
        )}
      </div>

      {/* 通道表单弹窗 */}
      {channelFormOpen && (
        <ChannelForm
          channel={editingChannel}
          onSave={handleSaveChannel}
          onClose={() => { setChannelFormOpen(false); setEditingChannel(null); }}
        />
      )}

      {/* 新增/编辑模型弹窗 */}
      {modelFormOpen && (
        <ModelForm
          onSave={editingModel ? handleUpdateModel : handleSaveModel}
          onClose={() => { setModelFormOpen(false); setEditingModel(null); }}
          editData={editingModel ? {
            model_id: editingModel.model_id,
            name: editingModel.name,
            category: editingModel.category,
            subcategory: editingModel.subcategory,
            service: editingModel.service,
          } : null}
        />
      )}

      <Toaster position="top-right" />
    </div>
  );
}

export default ModelManager;

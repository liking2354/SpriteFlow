import type {
  AssetItem,
  AssetGroup,
  AssetListResponse,
  ConfigResponse,
  GenerateRequest,
  GenerateResponse,
  GroupListResponse,
  HealthResponse,
  JobItem,
  JobListResponse,
  NodeSchema,
  PromptTemplate,
  TemplatePreviewRequest,
  TemplatePreviewResult,
  TemplateListResponse,
  RoutingResponse,
  StreamEvent,
  UpdateConfigRequest,
  UpdateRoutingRequest,
  VideoCreateInput,
  VideoListResponse,
  VideoStatus,
  VideoTaskItem,
  PipelineGraphModel,
  GraphListItem,
  GraphRunStatus,
  GraphRerunResponse,
  GraphRunListItem,
  VFCreateJobResponse,
  VFJobResponse,
  VFIndexData,
  VFProbeResponse,
  VFFramesList,
  VFCropParams,
  VFCropResponse,
  VFSaveFramesRequest,
  VFSaveFramesResponse,
  VFComposeRequest,
  VFComposeResponse,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      // 优先取 message（JSONResponse 格式），其次 detail（HTTPException 格式）
      if (body?.message) {
        detail = typeof body.message === "string" ? body.message : JSON.stringify(body.message);
        // 如果有校验错误，拼接详情
        if (body?.validation_errors && Array.isArray(body.validation_errors) && body.validation_errors.length > 0) {
          detail += ":\n" + body.validation_errors.join("; ");
        }
      } else if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {}

    // 分类友好的前端错误消息
    const friendly = _friendlyError(res.status, detail);
    throw new Error(friendly);
  }
  return res.json() as Promise<T>;
}

/** 将后端错误转换为用户友好的中文消息 */
function _friendlyError(status: number, detail: string): string {
  const msg = (detail || "").toString();

  // 已知错误码模式
  if (status === 401 || /缺[少失].*api.*key/i.test(msg) || /unauthorized/i.test(msg)) {
    return "API 密钥未配置或已失效，请检查 .env 文件中的 ARK_API_KEY";
  }
  if (/SensitiveContentDetected|内容安全/.test(msg)) {
    if (/prompt|提示词/i.test(msg)) return "提示词触发内容安全过滤，请修改描述后重试";
    if (/参考图|input/i.test(msg)) return "参考图被内容安全拦截，请更换图片后重试";
    if (/output|生成结果/i.test(msg)) return "生成结果被内容安全过滤，请重试";
    return "内容被安全系统拦截，请调整输入后重试";
  }
  if (/Seedream API 错误|provider/i.test(msg)) {
    return "AI 生成服务暂时不可用，请稍后重试";
  }
  if (/timeout|超时/i.test(msg)) {
    return "请求超时，请检查网络连接后重试";
  }
  if (/connect|network|dns|网络/i.test(msg)) {
    return "网络连接失败，请检查网络后重试";
  }
  if (status === 404) {
    return "请求的资源不存在";
  }
  if (status === 429) {
    return "请求过于频繁，请稍后重试";
  }
  if (status >= 500) {
    return "服务器内部错误，请稍后重试";
  }

  // 截断过长消息
  return msg.length > 150 ? msg.slice(0, 150) + "..." : msg;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  // Generate
  generate: (req: GenerateRequest) =>
    request<GenerateResponse>("/generate", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  startStream: (req: GenerateRequest) =>
    request<{ run_id: string; job_id: string }>("/generate/stream/start", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // Jobs
  listJobs: (params: { favorite?: boolean; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.favorite !== undefined) q.set("favorite", String(params.favorite));
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<JobListResponse>(`/jobs${qs ? `?${qs}` : ""}`);
  },
  getJob: (id: string) => request<JobItem>(`/jobs/${id}`),
  setJobFavorite: (id: string, favorite: boolean) =>
    request<{ status: string; favorite: boolean }>(`/jobs/${id}/favorite`, {
      method: "PUT",
      body: JSON.stringify({ favorite }),
    }),
  regenerateJob: (id: string) =>
    request<JobItem>(`/jobs/${id}/regenerate`, { method: "POST" }),
  deleteJob: (id: string) =>
    request<{ status: string }>(`/jobs/${id}`, { method: "DELETE" }),

  // Assets
  listAssets: (params: {
    source?: string;
    tags?: string;
    favorite?: boolean;
    group_id?: string;
    type?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.source) q.set("source", params.source);
    if (params.tags) q.set("tags", params.tags);
    if (params.favorite !== undefined) q.set("favorite", String(params.favorite));
    if (params.group_id !== undefined) q.set("group_id", params.group_id);
    if (params.type) q.set("type", params.type);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<AssetListResponse>(`/assets${qs ? `?${qs}` : ""}`);
  },
  getAsset: (id: string) => request<AssetItem>(`/assets/${id}`),
  getAssetChildren: (id: string) =>
    request<AssetListResponse>(`/assets/${id}/children`),
  deleteAsset: (id: string) =>
    request<{ status: string }>(`/assets/${id}`, { method: "DELETE" }),
  batchDeleteAssets: (assetIds: string[]) =>
    request<{ status: string; count: number }>("/assets/batch-delete", {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds }),
    }),
  batchMoveAssets: (assetIds: string[], groupId: string | null) =>
    request<{ status: string; count: number }>("/assets/batch-move", {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds, group_id: groupId }),
    }),
  setAssetGroup: (assetId: string, groupId: string | null) =>
    request<{ status: string }>(`/assets/${encodeURIComponent(assetId)}/group?group_id=${groupId ?? ""}`, { method: "PUT" }),
  setAssetFavorite: (id: string, favorite: boolean) =>
    request<{ status: string; favorite: boolean }>(`/assets/${id}/favorite`, {
      method: "PUT",
      body: JSON.stringify({ favorite }),
    }),
  uploadAsset: async (file: File, tags = "", parentId?: string, groupId?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("tags", tags);
    if (parentId) fd.append("parent_id", parentId);
    if (groupId) fd.append("group_id", groupId);
    const res = await fetch(`${BASE}/assets`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`upload failed: ${res.status}`);
    return res.json() as Promise<AssetItem>;
  },
  /** 覆盖原素材内容（保留 id/parent_id/tags/favorite） */
  replaceAssetContent: async (assetId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(
      `${BASE}/assets/${encodeURIComponent(assetId)}/content`,
      { method: "PUT", body: fd }
    );
    if (!res.ok) throw new Error(`replace failed: ${res.status}`);
    return res.json() as Promise<AssetItem>;
  },

  // Groups
  listGroups: () => request<GroupListResponse>("/groups"),
  createGroup: async (name: string, description = "") => {
    const fd = new FormData();
    fd.append("name", name);
    fd.append("description", description);
    const res = await fetch(`${BASE}/groups`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`create group failed: ${res.status}`);
    return res.json() as Promise<AssetGroup>;
  },
  updateGroup: async (id: string, name?: string, description?: string) => {
    const fd = new FormData();
    if (name !== undefined) fd.append("name", name);
    if (description !== undefined) fd.append("description", description);
    const res = await fetch(`${BASE}/groups/${encodeURIComponent(id)}`, { method: "PUT", body: fd });
    if (!res.ok) throw new Error(`update group failed: ${res.status}`);
    return res.json() as Promise<AssetGroup>;
  },
  deleteGroup: (id: string) =>
    request<{ status: string }>(`/groups/${encodeURIComponent(id)}`, { method: "DELETE" }),

  // Nodes / Routing
  listNodes: () => request<NodeSchema[]>("/nodes"),
  listNodesByCategory: (category?: string) => request<NodeSchema[]>(`/nodes${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  getRouting: () => request<RoutingResponse>("/routing"),
  updateRouting: (req: UpdateRoutingRequest) =>
    request<RoutingResponse>("/routing", {
      method: "PUT",
      body: JSON.stringify(req),
    }),
  reloadRouting: () =>
    request<RoutingResponse>("/routing/reload", { method: "POST" }),
  /** 获取 provider 配置（model / base_url / api_key 状态） */
  getConfig: () => request<ConfigResponse>("/config"),
  /** 更新 provider 配置 */
  updateConfig: (req: UpdateConfigRequest) =>
    request<{ status: string; updated: string[] }>("/config", {
      method: "PUT",
      body: JSON.stringify(req),
    }),

  // Videos
  createVideoTask: (req: VideoCreateInput) =>
    request<VideoTaskItem>("/videos/tasks", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  listVideoTasks: (params: { status?: VideoStatus | "all"; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status && params.status !== "all") q.set("status", params.status);
    if (params.limit) q.set("limit", String(params.limit));
    if (params.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<VideoListResponse>(`/videos/tasks${qs ? `?${qs}` : ""}`);
  },
  getVideoTask: (id: string) => request<VideoTaskItem>(`/videos/tasks/${id}`),
  cancelVideoTask: (id: string) =>
    request<VideoTaskItem>(`/videos/tasks/${id}/cancel`, { method: "POST" }),
  deleteVideoTask: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/videos/tasks/${id}`, { method: "DELETE" }),

  // Templates — 统一 API
  listTemplates: (params?: { type?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.type) q.set("type", params.type);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<TemplateListResponse>(`/templates${qs ? `?${qs}` : ""}`);
  },
  getTemplate: (id: string) => request<PromptTemplate>(`/templates/${id}`),
  createTemplate: (tpl: PromptTemplate) =>
    request<PromptTemplate>("/templates", {
      method: "POST",
      body: JSON.stringify(tpl),
    }),
  updateTemplate: (id: string, tpl: PromptTemplate) =>
    request<PromptTemplate>(`/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(tpl),
    }),
  deleteTemplate: (id: string) =>
    request<{ ok: boolean }>(`/templates/${id}`, { method: "DELETE" }),
  batchDeleteTemplates: (ids: string[]) =>
    request<{ ok: boolean; deleted: number }>("/templates/batch-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),

  // Templates — 按类型筛选
  listTemplatesByType: (type: string) =>
    request<TemplateListResponse>(`/templates/by-type/${type}`),

  // Templates — 预览
  previewTemplate: (req: TemplatePreviewRequest) =>
    request<TemplatePreviewResult>("/templates/preview", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  // Templates — 注入预置数据
  initTemplatePresets: () =>
    request<{ ok: boolean }>("/templates/init-presets", { method: "POST" }),

  // Graphs
  listGraphs: async (params?: { limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    const qs = q.toString();
    const res = await request<{ graphs: GraphListItem[]; total: number; limit: number; offset: number }>(
      `/graphs${qs ? `?${qs}` : ""}`
    );
    return res;
  },
  getGraph: (id: string) => request<PipelineGraphModel>(`/graphs/${id}`),
  createGraph: (graph: PipelineGraphModel) =>
    request<PipelineGraphModel>("/graphs", {
      method: "POST",
      body: JSON.stringify(graph),
    }),
  updateGraph: (id: string, graph: PipelineGraphModel) =>
    request<PipelineGraphModel>(`/graphs/${id}`, {
      method: "PUT",
      body: JSON.stringify(graph),
    }),
  deleteGraph: (id: string) =>
    request<{ status: string; id: string }>(`/graphs/${id}`, { method: "DELETE" }),
  searchGraphs: async (q: string) => {
    const params = new URLSearchParams({ q });
    const res = await request<{ graphs: GraphListItem[]; total: number }>(
      `/graphs/search?${params}`
    );
    return res.graphs;
  },
  /** 获取预设管线图列表 */
  listGraphPresets: () =>
    request<{ presets: Array<{ id: string; name: string; description: string; tags: string[]; node_count: number; edge_count: number }> }>(
      "/graphs/presets"
    ),
  /** 获取指定预设管线图完整数据 */
  getGraphPreset: (presetId: string) =>
    request<PipelineGraphModel>(`/graphs/presets/${presetId}`),
  runGraph: (req: { graph?: PipelineGraphModel; graph_id?: string }) =>
    request<GraphRunStatus>("/graphs/run", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  /** 运行已保存的管线图（按 graph_id） */
  runGraphById: (graphId: string) =>
    request<GraphRunStatus>(`/graphs/${graphId}/run`, { method: "POST" }),
  getGraphRun: (runId: string) =>
    request<GraphRunStatus>(`/graphs/runs/${runId}`),
  /** 历史运行列表 */
  listGraphRuns: (limit?: number) => {
    const qs = limit ? `?limit=${limit}` : "";
    return request<{ runs: GraphRunListItem[]; total: number }>(`/graphs/runs${qs}`);
  },
  /** 单节点重跑 */
  rerunGraphNode: (runId: string, nodeId: string, mode?: string) => {
    const qs = mode ? `?mode=${mode}` : "";
    return request<GraphRerunResponse>(`/graphs/runs/${runId}/rerun/${nodeId}${qs}`, {
      method: "POST",
    });
  },
  /** 冷启动执行单个节点（不需要先运行全图） */
  runGraphNode: (graphId: string, nodeId: string) => {
    return request<{ runId: string; graphId: string; nodeId: string; status: string }>(
      `/graphs/${graphId}/nodes/${nodeId}/run`,
      { method: "POST" },
    );
  },
  /** 获取图的最近一次运行结果（用于页面重进时恢复展示） */
  getGraphLatestRunResults: (graphId: string) =>
    request<import("./types").GraphLatestRunResults>(`/graphs/${graphId}/latest-run-results`),

  // ===== Video Frames (视频序列帧) =====
  /** 上传视频探测元数据 */
  probeVideo: async (file: File): Promise<VFProbeResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/video-frames/probe`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`probe failed: ${res.status}`);
    return res.json();
  },
  /** 创建抽帧任务 */
  createVFJob: async (file: File, params: {
    fps?: number; max_frames?: number;
    start_sec?: number; end_sec?: number;
    spacing?: number; layout_mode?: string; columns?: number;
    crop_left?: number; crop_right?: number;
    crop_top?: number; crop_bottom?: number;
  }): Promise<VFCreateJobResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("fps", String(params.fps ?? 8));
    fd.append("max_frames", String(params.max_frames ?? 16));
    if (params.start_sec) fd.append("start_sec", String(params.start_sec));
    if (params.end_sec) fd.append("end_sec", String(params.end_sec));
    fd.append("spacing", String(params.spacing ?? 4));
    fd.append("layout_mode", params.layout_mode ?? "auto_square");
    fd.append("columns", String(params.columns ?? 8));
    fd.append("crop_left", String(params.crop_left ?? 0));
    fd.append("crop_right", String(params.crop_right ?? 0));
    fd.append("crop_top", String(params.crop_top ?? 0));
    fd.append("crop_bottom", String(params.crop_bottom ?? 0));
    const res = await fetch(`${BASE}/video-frames/jobs`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`create failed: ${res.status}`);
    return res.json();
  },
  /** 查询抽帧任务 */
  getVFJob: (jobId: string) => request<VFJobResponse>(`/video-frames/jobs/${jobId}`),
  /** 获取抽帧结果索引 JSON */
  getVFIndex: async (jobId: string): Promise<VFIndexData> => {
    const res = await fetch(`${BASE}/video-frames/jobs/${jobId}/index`);
    if (!res.ok) throw new Error(`get index failed: ${res.status}`);
    return res.json();
  },
  /** 获取抽帧结果下载 URL（拼接到 BASE） */
  getVFResultUrl: (jobId: string, format = "png") => `${BASE}/video-frames/jobs/${jobId}/result?format=${format}`,
  /** 删除抽帧任务 */
  deleteVFJob: (jobId: string) => request<{ ok: boolean }>(`/video-frames/jobs/${jobId}`, { method: "DELETE" }),
  /** 获取抽帧任务的单帧文件列表 */
  getVFFrames: (jobId: string) => request<VFFramesList>(`/video-frames/jobs/${jobId}/frames`),
  /** 获取单帧图片 URL */
  getVFFrameUrl: (jobId: string, filename: string) => `${BASE}/video-frames/jobs/${jobId}/frames/${filename}`,
  /** 裁剪帧并重新合成 */
  cropVFJob: async (jobId: string, crop: VFCropParams): Promise<VFCropResponse> => {
    const q = new URLSearchParams({
      left: String(crop.left), top: String(crop.top),
      right: String(crop.right), bottom: String(crop.bottom),
    });
    const res = await fetch(`${BASE}/video-frames/jobs/${jobId}/crop?${q}`, { method: "POST" });
    if (!res.ok) throw new Error(`crop failed: ${res.status}`);
    return res.json();
  },

  /** AI 抠图单张图片 */
  matteImage: async (file: File): Promise<Blob> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/video-frames/matte`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`matte failed: ${res.status}`);
    return res.blob();
  },

  /** 创建水印去除任务 */
  createWatermarkJob: async (file: File): Promise<VFCreateJobResponse> => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/video-frames/watermark`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`watermark failed: ${res.status}`);
    return res.json();
  },
  /** 查询水印任务 */
  getWatermarkJob: (jobId: string) => request<VFJobResponse>(`/video-frames/watermark/${jobId}`),
  /** 获取去水印结果下载 URL */
  getWatermarkResultUrl: (jobId: string) => `${BASE}/video-frames/watermark/${jobId}/result`,
  /** 删除水印任务 */
  deleteWatermarkJob: (jobId: string) => request<{ ok: boolean }>(`/video-frames/watermark/${jobId}`, { method: "DELETE" }),

  /** 保存处理后的帧到后端 */
  saveVFrames: (jobId: string, req: VFSaveFramesRequest) =>
    request<VFSaveFramesResponse>(`/video-frames/jobs/${jobId}/save-frames`, {
      method: "POST",
      body: JSON.stringify(req),
    }),

  /** 重新合成精灵表 */
  composeVFSprite: (jobId: string, req: VFComposeRequest) =>
    request<VFComposeResponse>(`/video-frames/jobs/${jobId}/compose`, {
      method: "POST",
      body: JSON.stringify(req),
    }),
};

/** SSE 订阅 sequential 流式生成 */
export function subscribeGenerateStream(
  runId: string,
  onEvent: (evt: StreamEvent) => void,
  onError?: (err: Event) => void
): () => void {
  const es = new EventSource(`${BASE}/generate/stream/${runId}`);
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data) as StreamEvent);
    } catch {}
  };
  if (onError) es.onerror = onError;
  return () => es.close();
}

/** SSE 订阅管线图执行进度 */
const GRAPH_SSE_EVENT_TYPES = [
  "run_started", "node_queued", "node_started",
  "node_completed", "node_failed", "run_completed", "run_failed",
] as const;

export function subscribeGraphRunStream(
  runId: string,
  onEvent: (evt: { type: string; nodeId?: string; thumbnail?: string | null; error?: string | null; message?: string; assetId?: string | null; url?: string | null; cacheHit?: boolean; duration?: number; summary?: import("./types").GraphRunSummary | null }) => void,
  onError?: (err: Event) => void
): () => void {
  const es = new EventSource(`${BASE}/graphs/runs/${runId}/stream`);

  const handler = (e: MessageEvent) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch {}
  };

  // 监听所有命名事件（SSE event: 字段），注入 type 方便上游 switch
  for (const eventType of GRAPH_SSE_EVENT_TYPES) {
    es.addEventListener(eventType, (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data);
        onEvent({ ...data, type: eventType });
      } catch {}
    });
  }

  // 兜底：未命名消息或回退
  es.onmessage = handler;

  if (onError) es.onerror = onError;
  return () => es.close();
}

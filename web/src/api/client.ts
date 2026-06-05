import type {
  AssetItem,
  AssetGroup,
  AssetListResponse,
  GenerateRequest,
  GenerateResponse,
  GroupListResponse,
  HealthResponse,
  JobItem,
  JobListResponse,
  NodeSchema,
  RoutingResponse,
  StreamEvent,
  VideoCreateInput,
  VideoListResponse,
  VideoStatus,
  VideoTaskItem,
  WorkflowRunResponse,
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
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
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

  /** AI 图像处理（火山引擎） */
  aiProcess: async (assetId: string, capability: string, params: Record<string, unknown> = {}) => {
    const res = await fetch(`${BASE}/assets/ai-process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: assetId, capability, ...params }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail || `${res.status} ${res.statusText}`);
    }
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

  // Nodes / Routing / Workflows
  listNodes: () => request<NodeSchema[]>("/nodes"),
  getRouting: () => request<RoutingResponse>("/routing"),
  submitWorkflow: (yamlPath: string) =>
    request<WorkflowRunResponse>("/workflows", {
      method: "POST",
      body: JSON.stringify({ yaml_path: yamlPath }),
    }),
  getRun: (runId: string) => request<WorkflowRunResponse>(`/runs/${runId}`),

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

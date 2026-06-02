import type {
  AssetItem,
  AssetListResponse,
  GenerateRequest,
  GenerateResponse,
  HealthResponse,
  JobItem,
  JobListResponse,
  NodeSchema,
  RoutingResponse,
  StreamEvent,
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
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.source) q.set("source", params.source);
    if (params.tags) q.set("tags", params.tags);
    if (params.favorite !== undefined) q.set("favorite", String(params.favorite));
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
  setAssetFavorite: (id: string, favorite: boolean) =>
    request<{ status: string; favorite: boolean }>(`/assets/${id}/favorite`, {
      method: "PUT",
      body: JSON.stringify({ favorite }),
    }),
  uploadAsset: async (file: File, tags = "", parentId?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("tags", tags);
    if (parentId) fd.append("parent_id", parentId);
    const res = await fetch(`${BASE}/assets`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`upload failed: ${res.status}`);
    return res.json() as Promise<AssetItem>;
  },

  // Nodes / Routing / Workflows
  listNodes: () => request<NodeSchema[]>("/nodes"),
  getRouting: () => request<RoutingResponse>("/routing"),
  submitWorkflow: (yamlPath: string) =>
    request<WorkflowRunResponse>("/workflows", {
      method: "POST",
      body: JSON.stringify({ yaml_path: yamlPath }),
    }),
  getRun: (runId: string) => request<WorkflowRunResponse>(`/runs/${runId}`),
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

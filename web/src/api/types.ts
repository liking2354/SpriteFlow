/* 后端 API 类型定义 */

export type GenerateMode =
  | "text2img"
  | "img2img"
  | "multi_fusion"
  | "sequential";

export interface GenerateRequest {
  mode: GenerateMode;
  prompt: string;
  image_urls?: string[];
  ref_asset_ids?: string[];
  size?: string;
  width?: number | null;
  height?: number | null;
  seed?: number | null;
  max_images?: number;
  web_search?: boolean;
  watermark?: boolean;
  save_as_asset?: boolean;
  tags?: string[];
  group_id?: string | null;
}

export interface GeneratedImage {
  url: string;
  asset_id?: string;
  width?: number;
  height?: number;
  thumbnail?: string | null;
  favorite?: boolean;
}

export interface GenerateResponse {
  job_id: string;
  images: GeneratedImage[];
  usage: {
    generated_images?: number;
    output_tokens?: number;
    total_tokens?: number;
    [k: string]: unknown;
  };
  model?: string | null;
}

export interface AssetItem {
  id: string;
  type: string;
  source: "uploaded" | "generated" | "derived" | "ai_processed";
  uri: string;
  hash: string;
  width?: number;
  height?: number;
  thumbnail?: string | null;
  tags: string[];
  parent_id?: string | null;
  group_id?: string | null;
  provenance?: Record<string, unknown> | null;
  favorite?: boolean;
  created_at: string;
}

export interface AssetGroup {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface AssetListResponse {
  items: AssetItem[];
  total: number;
}

export interface GroupListResponse {
  items: AssetGroup[];
}

/** 创作任务（持久化记录） */
export interface JobItem {
  id: string;
  mode: GenerateMode;
  prompt: string;
  params: {
    size?: string;
    width?: number | null;
    height?: number | null;
    seed?: number | null;
    max_images?: number;
    web_search?: boolean;
    watermark?: boolean;
    tags?: string[];
  };
  ref_image_urls: string[];
  ref_asset_ids: string[];
  asset_ids: string[];
  status: "pending" | "running" | "completed" | "failed";
  error: string | null;
  favorite: boolean;
  model: string | null;
  usage: Record<string, unknown> | null;
  parent_id: string | null;
  created_at: string;
  finished_at: string | null;
  /** 后端附带：每张输出图的预签名 URL（含再次生成的子任务输出） */
  assets: Array<{
    id: string;
    url: string;
    thumbnail?: string | null;
    width?: number;
    height?: number;
    favorite?: boolean;
    tags?: string[];
  }>;
  /** 后端附带：参考图（asset 或 url）的预签名 URL */
  ref_assets: Array<{
    asset_id: string | null;
    url: string;
    thumbnail?: string | null;
    width?: number;
    height?: number;
    origin: "asset" | "url";
  }>;
  /** 后端附带：再次生成的占位/子任务（pending/running/failed） */
  pending_children: Array<{
    job_id: string;
    status: "pending" | "running" | "failed";
    error?: string | null;
    created_at: string;
  }>;
}

export interface JobListResponse {
  items: JobItem[];
  total: number;
}

export interface NodeSchema {
  type: string;
  category: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
  params: Array<{
    name: string;
    type: string;
    default: unknown;
    required: boolean;
    min: number | null;
    max: number | null;
    choices: string[] | null;
  }>;
}

export interface RoutingResponse {
  routes: Record<string, string>;
  providers: Array<{ name: string; capabilities: string[] }>;
}

export interface WorkflowRunResponse {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  results: Record<
    string,
    {
      status: "pending" | "running" | "completed" | "failed";
      cache_hit: boolean;
      error?: string | null;
    }
  >;
}

export interface HealthResponse {
  status: string;
  version: string;
  model: string;
  ark_configured: boolean;
}

export interface StreamEvent {
  type: string;
  index?: number;
  url?: string;
  size?: string;
  asset_id?: string;
  width?: number;
  height?: number;
  thumbnail?: string;
  images?: GeneratedImage[];
  usage?: Record<string, unknown>;
  model?: string;
  message?: string;
  run_id?: string;
  job_id?: string;
}

// ============================ 视频生成 ============================

export type VideoMode =
  | "text2video"
  | "image2video_first"
  | "first_last"
  | "multi_ref";

export type VideoStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "expired";

export interface VideoCreateInput {
  mode: VideoMode;
  prompt: string;
  first_frame_asset_id?: string | null;
  last_frame_asset_id?: string | null;
  ref_asset_ids?: string[];
  model?: string | null;
  ratio?: string | null;
  resolution?: string | null;
  duration?: number | null;
  seed?: number | null;
  camerafixed?: boolean | null;
  watermark?: boolean | null;
  return_last_frame?: boolean | null;
  generate_audio?: boolean | null;
  execution_expires_after?: number | null;
}

export interface VideoTaskItem {
  id: string;
  provider: string;
  provider_task_id: string | null;
  model: string;
  mode: VideoMode;
  prompt: string;
  params: Record<string, unknown>;
  status: VideoStatus;
  error: string | null;
  result_asset: AssetItem | null;
  last_frame_asset: AssetItem | null;
  inputs: {
    first_frame_asset_id?: string | null;
    last_frame_asset_id?: string | null;
    ref_asset_ids?: string[];
  };
  usage_tokens: number | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface VideoListResponse {
  items: VideoTaskItem[];
  total: number;
  limit: number;
  offset: number;
}

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
  text_preview?: string | null;
  duration?: number | null;
  mime_type?: string | null;
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

export type NodeParamWidget = "text" | "textarea" | "number" | "select" | "multi_select" | "size" | "toggle";

export interface NodeParamSchema {
  name: string;
  type: string;
  label?: string;
  widget?: NodeParamWidget | string;
  default: unknown;
  required: boolean;
  min: number | null;
  max: number | null;
  choices: string[] | null;
  placeholder?: string | null;
  help?: string | null;
  options_source?: "specs" | "characters" | "actions" | "vfx" | "templates" | string | null;
  multiple?: boolean;
}

export interface NodeSchema {
  type: string;
  label?: string;
  icon?: string;
  color?: string;
  description?: string;
  category: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
  params: NodeParamSchema[];
}

export interface RoutingResponse {
  routes: Record<string, string>;
  fallback?: Record<string, string[]>;
  providers: Array<{ name: string; capabilities: string[] }>;
}

/** Provider 配置（可编辑） */
export interface ProviderConfig {
  name: string;
  capabilities: string[];
  model?: string;
  base_url?: string;
  api_key_configured: boolean;
  api_key_masked: string;
}

/** 统一配置响应 */
export interface ConfigResponse {
  providers: Record<string, ProviderConfig>;
}

/** 更新路由请求 */
export interface UpdateRoutingRequest {
  routes?: Record<string, string>;
  fallback?: Record<string, string[]>;
}

/** 更新 Provider 配置请求 */
export interface UpdateConfigRequest {
  providers: Record<
    string,
    {
      model?: string;
      base_url?: string;
      api_key?: string;
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
export interface BatchMatrixEntry {
  char: string;
  action: string;
  char_id: string;
  action_id: string;
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
}

export interface BatchStatusResponse {
  batch_id: string;
  status: "running" | "completed" | "failed" | "partial";
  total_jobs: number;
  completed: number;
  failed: number;
  matrix: BatchMatrixEntry[];
}

// ============================ 视频序列帧 ============================

export type VFJobStatus = "processing" | "completed" | "failed";

export interface VFExtractParams {
  fps: number;
  max_frames: number;
  start_sec: number;
  end_sec: number;
  spacing: number;
  layout_mode: string;
  columns: number;
  crop_left?: number;
  crop_right?: number;
  crop_top?: number;
  crop_bottom?: number;
}

export interface VFJobResult {
  sprite_path?: string;
  index_path?: string;
  frame_count?: number;
  frame_size?: { w: number; h: number };
  sheet_size?: { w: number; h: number };
  output?: string;
}

export interface VFJobResponse {
  id: string;
  status: VFJobStatus;
  progress: number;
  params?: VFExtractParams;
  error?: { message?: string } | null;
  result?: VFJobResult | null;
}

export interface VFCreateJobResponse {
  job_id: string;
  status: string;
}

export interface VFIndexData {
  version: string;
  frame_size: { w: number; h: number };
  sheet_size: { w: number; h: number };
  frames: Array<{
    i: number;
    x: number;
    y: number;
    w: number;
    h: number;
    t: number;
  }>;
}

/** 视频探针响应 */
export interface VFProbeResponse {
  duration: number;
  width: number;
  height: number;
  original_fps: number;
  frame_count: number;
  filename: string;
  size_mb: number;
}

/** 帧文件列表 */
export interface VFFramesList {
  frames: Array<{ name: string; url: string }>;
  frame_count: number;
}

/** 裁剪参数 */
export interface VFCropParams {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** 裁剪响应 */
export interface VFCropResponse {
  status: string;
  frame_size: { w: number; h: number };
  sheet_size: { w: number; h: number };
  frame_count: number;
  crop: VFCropParams;
}

/** 保存帧请求 */
export interface VFSaveFramesRequest {
  frames: string[]; // base64 PNG 数据
}

/** 保存帧响应 */
export interface VFSaveFramesResponse {
  status: string;
  saved: number;
  frame_size?: { w: number; h: number } | null;
}

/** 重新合成请求 */
export interface VFComposeRequest {
  columns: number;
  margin: number;
  spacing: number;
  cell_size: number;
  smooth: boolean;
}

/** 重新合成响应 */
export interface VFComposeResponse {
  status: string;
  frame_count: number;
  frame_size: { w: number; h: number };
  sheet_size: { w: number; h: number };
}

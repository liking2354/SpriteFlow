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

export interface WorkflowRunResponse {
  runId: string;
  status: "pending" | "running" | "completed" | "failed";
  results: Record<
    string,
    {
      status: "pending" | "running" | "completed" | "failed";
      cacheHit: boolean;
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

// ============================ 模板系统（统一单表模型）============================

export type TemplateType = "spec" | "character" | "direction" | "action" | "vfx" | "custom";

export type SlotType = "input" | "dropdown";

export interface PromptSlot {
  name: string;
  type: SlotType;
  label: string;
  default: string;
  options: string[];
  placeholder: string;
}

export interface PromptTemplate {
  id: string;
  name: string;
  type: TemplateType;
  text: string;
  slots: PromptSlot[];
  description: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface TemplatePreviewRequest {
  template_ids: string[];
  slot_values: Record<string, string>;
}

export interface TemplatePreviewLayer {
  template_id: string;
  template_name: string;
  type: string;
  filled_text: string;
}

export interface TemplatePreviewResult {
  layers: TemplatePreviewLayer[];
  final_prompt: string;
}

export interface TemplateListResponse {
  templates: PromptTemplate[];
  total: number;
  limit: number;
  offset: number;
}

// 向后兼容：保留旧类型别名（标记为废弃）
/** @deprecated 请使用 PromptTemplate */
export interface CharacterTemplate {
  id: string;
  name: string;
  key: string;
  description: string;
  color_scheme: string[];
  build_type: string;
  class_type: string;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** @deprecated 请使用 PromptTemplate */
export interface ActionTemplate {
  id: string;
  name: string;
  key: string;
  action_type: string;
  prompt: string;
  directions: number;
  frames_per_direction: number;
  total_frames: number;
  description: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/** @deprecated 请使用 PromptTemplate */
export interface SpriteSpec {
  id: string;
  name: string;
  description: string;
  canvas: Record<string, unknown>;
  align: Record<string, unknown>;
  layers: Record<string, unknown>[];
  default_format: string;
  default_group_id: string | null;
  default_character_template_ids: string[];
  default_action_template_ids: string[];
  version: number;
  is_active: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/** @deprecated 请使用 PromptTemplate */
export interface VFXTemplate {
  id: string;
  name: string;
  key: string;
  vfx_type: string;
  prompt: string;
  frames: number;
  canvas_width: number;
  canvas_height: number;
  description: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/** @deprecated 请使用 TemplatePreviewRequest */
export interface PromptAssembly {
  spec_id: string;
  character_template_id: string;
  action_template_id: string;
  override_char_desc?: string | null;
  override_action_prompt?: string | null;
  extra_layers?: string[];
  extra_negative?: string | null;
}

/** @deprecated 请使用 TemplatePreviewResult */
export interface PromptAssemblyResult {
  layers: PromptLayerInfo[];
  final_prompt: string;
  final_negative: string;
  spec_id: string;
  character_name: string;
  action_name: string;
}

/** @deprecated 旧模型 */
export interface PromptBlock {
  id: string;
  name: string;
  content: string;
  category: string;
  description: string;
  sort_order: number;
  enabled: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/** @deprecated 旧模型 */
export interface PromptLayer {
  id: string;
  name: string;
  category: string;
  description: string;
  blocks: PromptBlock[];
  sort_order: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** @deprecated 旧模型 */
export interface BlockInfo {
  block_name: string;
  category: string;
  content: string;
  enabled: boolean;
}

/** @deprecated 旧模型 */
export interface PromptLayerInfo {
  layer_name: string;
  category: string;
  blocks: BlockInfo[];
  combined: string;
}

export interface BatchGenerateRequest {
  spec_id: string;
  pipeline_id?: string | null;
  character_template_ids: string[];
  action_template_ids: string[];
  vfx_template_ids?: string[];
  generate_count_per?: number;
  concurrent?: number;
  group_id?: string | null;
}

export interface BatchGenerateResponse {
  batch_id: string;
  total_jobs: number;
  jobs: BatchMatrixEntry[];
  status: string;
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

// ============================ VFX 特效（已合并到模板系统）============================

export type VFXType = "projectile" | "aoe" | "buff" | "self_cast" | "explosion";

/** @deprecated 请使用 PromptTemplate */
export interface VFXGenerateRequest {
  vfx_template_id: string;
  seed?: number | null;
  group_id?: string | null;
}

/** @deprecated 旧模型 */
export interface VFXFrameEntry {
  frame_index: number;
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  asset_id?: string | null;
  url?: string | null;
}

/** @deprecated 旧模型 */
export interface VFXGenerateResponse {
  vfx_id: string;
  batch_id: string;
  vfx_name: string;
  total_frames: number;
  frames: VFXFrameEntry[];
  status: string;
  completed: number;
  failed: number;
}

// ============================ 管线图 ============================

export interface PipelineNodeParams {
  [key: string]: unknown;
  template_ids?: string;
  slot_values?: Record<string, string>;
  style_prompt?: string;
  max_images?: number;
  size?: string;
  canvas_width?: number;
  canvas_height?: number;
  target_width?: number;
  target_height?: number;
  seed?: number | null;
  watermark?: string;
  output_format?: string;
}

export interface PipelineNodeModel {
  id: string;
  type: string;
  x: number;
  y: number;
  width?: number | null;
  height?: number | null;
  collapsed?: boolean;
  params: PipelineNodeParams;
  ui?: Record<string, unknown>;
}

export interface GraphEdgeModel {
  id: string;
  src_node: string;
  src_port: string;
  dst_node: string;
  dst_port: string;
}

export interface PipelineGraphModel {
  schema_version?: number;
  id: string;
  name: string;
  description: string;
  spec_id?: string | null;
  nodes: PipelineNodeModel[];
  edges: GraphEdgeModel[];
  viewport?: Record<string, unknown>;
  tags: string[];
  created_at?: string;
  updated_at?: string;
}

export interface GraphListItem {
  id: string;
  name: string;
  description: string;
  tags: string[];
  spec_id?: string | null;
  node_count: number;
  created_at: string;
  updated_at: string;
}

export interface GraphRunStatus {
  runId: string;
  graphName?: string;
  status: "pending" | "running" | "completed" | "failed";
  startedAt?: string | null;
  finishedAt?: string | null;
  results?: Record<
    string,
    {
      status: string;
      cacheHit?: boolean;
      error?: string | null;
      assetId?: string | null;
      url?: string | null;
      nodeType?: string;
      inputs?: Record<string, unknown> | null;
    }
  >;
}

export type GraphRunEventType =
  | "run_started"
  | "run_completed"
  | "run_failed"
  | "node_queued"
  | "node_started"
  | "node_completed"
  | "node_failed";

export interface GraphRunEvent {
  type: GraphRunEventType;
  nodeId?: string;
  nodeType?: string;
  thumbnail?: string | null;
  error?: string | null;
  message?: string;
  assetId?: string | null;
  url?: string | null;
  cacheHit?: boolean;
  duration?: number;
  /** 执行输入快照（prompt/params/template_ids 等） */
  inputs?: Record<string, unknown> | null;
  /** run_completed 事件中包含的运行摘要 */
  summary?: GraphRunSummary | null;
}

/** 运行摘要 */
export interface GraphRunSummary {
  duration: number;
  successCount: number;
  failedCount: number;
  cacheHits: number;
  assets: Array<{
    nodeId: string;
    assetId: string;
    url?: string | null;
  }>;
  failedNodes: Array<{
    nodeId: string;
    error?: string | null;
  }>;
}

/** 图最近运行结果（用于页面重进恢复） */
export interface GraphLatestRunResults {
  runId: string | null;
  status: string | null;
  finishedAt: string | null;
  nodeResults: Record<
    string,
    {
      status: string;
      cacheHit: boolean;
      error?: string | null;
      assetId?: string | null;
      thumbnail?: string | null;
      url?: string | null;
      nodeType?: string;
      inputs?: Record<string, unknown> | null;
    }
  >;
}

/** 单节点重跑响应 */
export interface GraphRerunResponse {
  runId: string;
  nodeId: string;
  rerunNodes: string[];
  status: string;
  results: Record<
    string,
    {
      status: string;
      cacheHit: boolean;
      error?: string | null;
      assetId?: string | null;
      url?: string | null;
      nodeType?: string;
      inputs?: Record<string, unknown> | null;
    }
  >;
}

/** 历史运行记录列表项 */
export interface GraphRunListItem {
  runId: string;
  graphId?: string | null;
  graphName?: string;
  status: string;
  startedAt?: string;
  finishedAt?: string;
  summary?: GraphRunSummary | null;
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

/** 渲染端业务类型。与 api/schemas.py 保持字段名一致（snake_case）。 */

export type ThemeName = 'LIGHT' | 'DARK';

export type AgentThinkingLevel = 'OFF' | 'LOW' | 'MEDIUM' | 'HIGH' | 'MAX';

export interface AgentToolEntry {
  name: string;
  status: 'running' | 'done' | 'failed' | 'cancelled';
  arguments?: Record<string, unknown>;
  message?: string;
  code?: string;
  data?: Record<string, unknown>;
  progress?: {
    stage: string;
    percent: number;
    detail: string;
  };
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  tools?: AgentToolEntry[];
  status?: 'running' | 'done' | 'failed' | 'cancelled';
  error?: string;
}

export interface AgentSnapshot {
  session_id: string;
  revision: number;
  run_id: number;
  status: 'idle' | 'running' | 'stopping';
  messages: AgentMessage[];
  confirmation: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
    data: Record<string, unknown>;
    expires_at: number;
  } | null;
  stage?: string;
  budget?: {
    context_window?: number;
    max_output_tokens?: number;
    usable_tokens?: number;
    max_context_chars?: number;
    max_messages?: number;
    max_iterations?: number;
  };
  /** 本轮用量统计：状态栏的轮次、步数、吞吐与上下文占比。 */
  metrics?: {
    iterations?: number;
    steps?: number;
    requests?: number;
    input_tokens?: number;
    output_tokens?: number;
    cached_tokens?: number;
    total_tokens?: number;
    elapsed_seconds?: number;
    tokens_per_second?: number;
    cache_hit_rate?: number | null;
    context_chars?: number;
    context_limit_chars?: number;
    context_percent?: number;
  };
}

/** 项目翻译状态：Base.TranslationStatus 的项目级取值 */
export type ProjectStatus = 'UNTRANSLATED' | 'TRANSLATING' | 'TRANSLATED';

/**
 * 可作为启动目标的翻译状态。
 * TRANSLATED 表示已完成，没有对应的启动入口（PyQt 页的「开始」按钮此时禁用），
 * 所以后端与前端都不接受它作为 start 的入参。
 */
export type StartableProjectStatus = 'UNTRANSLATED' | 'TRANSLATING';

/** 工具箱翻译方式：与 api/schemas.TRANSLATION_TOOLBOX_MODES 对齐（hook 走独立路由） */
export type TranslationToolboxMode = 'direct' | 'source' | 'supplement';

/** 带 mode 时后端原子写入路径/开关后再 TRANSLATION_START */
export interface TranslationStartOptions {
  requestId?: string;
  preflightConfirmed?: boolean;
  /** 当前绑定项目 owner；与手动 target 分开 */
  project_key?: string;
  mode?: TranslationToolboxMode;
  game_path?: string;
  tl_parent?: string;
  tl_name?: string;
  language?: string;
  input_folder?: string;
  output_folder?: string;
  source_language?: string;
  target_language?: string;
  traditional_chinese_enable?: boolean;
  renpy_backup_original?: boolean;
  auto_write_back?: boolean;
  external_backup_dir?: string;
  renpy_hook_incremental?: boolean;
  generate_empty?: boolean;
}

/** 手动写回选定 TL 缓存 */
export interface TranslationReinjectOptions {
  output_folder?: string;
  tl_parent?: string;
  tl_name?: string;
  game_path?: string;
  project_key?: string;
  request_id?: string;
}

export interface HookTranslateStartOptions {
  game_path: string;
  tl_name?: string;
  source_language?: string;
  target_language?: string;
  traditional_chinese_enable?: boolean;
  renpy_backup_original?: boolean;
  renpy_hook_incremental?: boolean;
  generate_empty?: boolean;
  preflight_confirmed?: boolean;
  project_key?: string;
  request_id?: string;
}

export interface HookTranslateStartResponse {
  accepted: boolean;
  reason?: string;
  detail?: string;
  request_id?: string;
  job?: JobSnapshot | null;
}

/** 引擎状态：Engine.Status */
export type EngineStatus =
  | 'IDLE'
  | 'TESTING'
  | 'TRANSLATING'
  | 'QUALITY'
  | 'AGENT'
  | 'STOPPING';

export interface HealthInfo {
  ok: boolean;
  pid: number;
  mode: string;
  app_version: string;
  python_version?: string;
  config_path?: string;
}

export interface VersionInfo {
  app_version: string;
  api_version: string;
}

export type UpdateStatus = 'NONE' | 'NEW_VERSION' | 'DESKTOP_AVAILABLE' | 'UPDATING' | 'DOWNLOADED';

export interface UpdateState {
  ok?: boolean;
  status: UpdateStatus | string;
  version: string;
  latest: {
    tag_name?: string;
    body?: string;
    published_at?: string;
    /** desktop = 需前往发布页安装桌面版，不可走 Python 自动更新 */
    delivery?: string;
    /** 后端 _normalize_release 选出的下载资源，含真实 asset.size */
    asset?: { name?: string; size?: number; browser_download_url?: string; digest?: string };
    assets?: { name?: string; size?: number; browser_download_url?: string; digest?: string }[];
  };
  downloaded_size: number;
  total_size: number;
  error: string;
  new_version: boolean;
  release_url: string;
  can_install: boolean;
}

export interface ChangelogResponse {
  markdown: string;
  empty: boolean;
}

export interface SettingsResponse {
  values: Record<string, unknown>;
  masked: string[];
}

export interface ProjectInfo {
  renpy_project_path: string;
  renpy_game_folder: string;
  renpy_tl_folder: string;
  theme: string;
  app_language: string;
}

export interface ProjectFileInfo {
  path: string;
  schema_version: number;
  app_version: string;
  created_at: string;
  updated_at: string;
  project_root: string;
  item_count: number;
  items_digest: string;
}

export interface ProjectFileResponse {
  info: ProjectFileInfo;
  output_folder: string;
  current_project_root: string;
  project_root_matches: boolean;
  settings?: string[];
  backup_folder?: string;
  assets_output_folder?: string;
  assets_backup_folder?: string;
  item_count?: number;
  applied_settings?: string[];
  ignored_settings?: string[];
}

/** POST /api/project/file/inspect */
export interface ProjectFileDescription {
  info: ProjectFileInfo;
  /** 当前配置解析出的翻译输出目录；没有时为空串 */
  output_folder: string;
  current_project_root: string;
  project_root_matches: boolean;
}

/** POST /api/project/file/export */
export interface ProjectFileExportResult extends ProjectFileDescription {
  settings: string[];
}

/** POST /api/project/file/legacy/inspect */
export interface LegacyProjectCacheDescription {
  output_folder: string;
  cache_folder: string;
  cache_format: 'sqlite' | 'json';
  item_count: number;
  current_project_root: string;
  /** 仅携带当前应用中的项目翻译设置，未读取旧版程序配置 */
  settings: string[];
}

/** POST /api/project/file/legacy/export */
export interface LegacyProjectFileExportResult extends ProjectFileExportResult {
  source_output_folder: string;
}

/** POST /api/project/file/import */
export interface ProjectFileImportResult extends ProjectFileDescription {
  /** 导入前缓存的回滚备份目录；导入前没有缓存时为空串 */
  backup_folder: string;
  /** 工作台资料所在的规范输出目录；与当前输出目录相同（无需单独同步）时为空串 */
  assets_output_folder: string;
  /** 规范输出目录导入前缓存的回滚备份；未同步或导入前没有缓存时为空串 */
  assets_backup_folder: string;
  item_count: number;
  applied_settings: string[];
  ignored_settings: string[];
}

export type JobStatus = 'pending' | 'running' | 'done' | 'failed' | 'cancelled';

export interface JobSnapshot {
  id: string;
  kind: string;
  status: JobStatus;
  total: number;
  done: number;
  progress: number;
  error: string | null;
  created_at: number;
  updated_at: number;
  result?: unknown;
}

export interface TranslationState {
  engine_status: EngineStatus;
  stop_barrier: boolean;
  single_tasks: boolean;
  /** 当前绑定项目的 owner key；写操作（停止 / 导出 / 重试失败项）要带上它。 */
  owner_project_key?: string;
  request_id: string;
  run_id: number;
  running: { running: number; max: number };
  progress: Record<string, unknown>;
  active_output_folder: string;
  progress_source?: 'none' | 'runtime' | 'cache';
  progress_error?: string;
}

export interface TranslationStartResponse {
  accepted: boolean;
  reason: 'STARTED' | 'STOPPING' | 'ENGINE_BUSY' | 'ASSETS_MISSING' | 'PREPARE_FAILED' | string;
  detail?: string;
  request_id?: string;
  warnings?: string[];
  stage?: string;
  job?: JobSnapshot | null;
}

export interface TokenEstimate {
  total_source_tokens: number;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_cost: number;
  batch_count: number;
  untranslated_count: number;
}

/** WS 事件负载：TRANSLATION_UPDATE 等进度事件的字段按需读取 */
export interface TranslationUpdateData {
  phase?: string;
  message?: string;
  line?: number;
  total_line?: number;
  total_tokens?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  failed_line_count?: number;
  fallback_line_count?: number;
  line_count_mismatch_count?: number;
  requested_line_count?: number;
  processed_batches?: number;
  request_count?: number;
  total_latency_ms?: number;
  latency_ms?: number;
  cached_line_count?: number;
  cache_hit_rate?: number;
  throughput?: number | Record<string, unknown>;
  time?: number;
  recent_items?: unknown[];
  [key: string]: unknown;
}

export interface WsEventMessage {
  type: 'event';
  event: string;
  data: Record<string, unknown>;
}

export interface WsJobMessage {
  type: 'job';
  job: JobSnapshot;
}

export interface WsHelloMessage {
  type: 'hello';
  app_version: string;
  events: string[];
}

export type WsMessage = WsHelloMessage | WsEventMessage | WsJobMessage | { type: string; [key: string]: unknown };

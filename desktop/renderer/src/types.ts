/** 渲染端业务类型。与 api/schemas.py 保持字段名一致（snake_case）。 */

export type ThemeName = 'LIGHT' | 'DARK';

/** 项目翻译状态：Base.TranslationStatus 的项目级取值 */
export type ProjectStatus = 'UNTRANSLATED' | 'TRANSLATING' | 'TRANSLATED';

/**
 * 可作为启动目标的翻译状态。
 * TRANSLATED 表示已完成，没有对应的启动入口（PyQt 页的「开始」按钮此时禁用），
 * 所以后端与前端都不接受它作为 start 的入参。
 */
export type StartableProjectStatus = 'UNTRANSLATED' | 'TRANSLATING';

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

export interface JobSnapshot {
  id: string;
  kind: string;
  status: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'CANCELLED';
  total: number;
  done: number;
  result: unknown;
  error: string | null;
  created_at: string;
  updated_at: string;
  progress: number;
}

export interface TranslationState {
  engine_status: EngineStatus;
  stop_barrier: boolean;
  single_tasks: boolean;
  request_id: string;
  run_id: number;
  running: { running: number; max: number };
  progress: Record<string, unknown>;
  active_output_folder: string;
}

export interface TranslationStartResponse {
  accepted: boolean;
  reason: 'STARTED' | 'STOPPING' | 'ENGINE_BUSY' | 'ASSETS_MISSING' | 'PREPARE_FAILED';
  detail?: string;
  request_id?: string;
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

export interface WsHelloMessage {
  type: 'hello';
  app_version: string;
  events: string[];
}

export type WsMessage = WsHelloMessage | WsEventMessage | { type: string; [key: string]: unknown };

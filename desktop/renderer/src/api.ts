/**
 * sidecar 业务接口客户端。
 *
 * 所有路由都对应 api/ 下真实存在的 FastAPI 路由；没有 mock 数据。
 * 后端 4xx/5xx 时把 detail 原文带出来 —— 界面直接显示它，
 * 不再自己编一套「出错了」文案把真实原因盖掉。
 */

import type {
  AgentSnapshot,
  AgentThinkingLevel,
  ChangelogResponse,
  HealthInfo,
  HookTranslateStartOptions,
  HookTranslateStartResponse,
  JobSnapshot,
  LegacyProjectCacheDescription,
  LegacyProjectFileExportResult,
  ProjectFileBinding,
  ProjectFileCreateResult,
  ProjectFileDescription,
  ProjectFileExportResult,
  ProjectFileImportResult,
  ProjectInfo,
  SettingsResponse,
  StartableProjectStatus,
  StoryBlueprintLabelDetail,
  StoryBlueprintReadiness,
  StoryBlueprintResponse,
  TokenEstimate,
  TranslationReinjectOptions,
  TranslationResumableInfo,
  TranslationStartOptions,
  TranslationStartResponse,
  TranslationState,
  UpdateState,
  VersionInfo,
} from './types';

export interface GlossaryRow {
  src: string;
  dst: string;
  info?: string;
  regex?: boolean;
  case_sensitive?: boolean;
}

export interface GlossaryRows {
  kind: string;
  rows: GlossaryRow[];
  total: number;
}

/** 后端错误：保留 HTTP 状态码与 detail，界面据此区分「冲突」与「失败」。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }

  /** 409：状态冲突（引擎忙、正在停止），界面应提示而非报错。 */
  get isConflict(): boolean {
    return this.status === 409;
  }
}

/**
 * 后端基址。
 *
 * dev：窗口从 vite dev server 加载，同源相对路径由 vite.config.ts 的 proxy
 * 转发到 sidecar。
 * 打包：窗口是 file:// 源，没有 origin，相对路径会解析成 file:///api/... 而
 * 全部失败，必须走绝对地址。
 */
const SIDECAR_ORIGIN = `http://127.0.0.1:${window.renpy?.sidecarPort || 9712}`;

export function apiBase(): string {
  const { protocol, host } = window.location;
  return protocol === 'file:' || !host ? SIDECAR_ORIGIN : '';
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }
  return (await res.json()) as T;
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      // FastAPI 参数校验错误：[{loc, msg, type}]
      return body.detail
        .map((item) => {
          const entry = item as { loc?: unknown[]; msg?: string };
          const field = (entry.loc ?? []).slice(1).join('.');
          return field ? `${field}: ${entry.msg ?? ''}` : (entry.msg ?? '');
        })
        .join('；');
    }
  } catch {
    // 响应不是 JSON：退回状态文案
  }
  return `请求失败（HTTP ${res.status}）`;
}

export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('/health');
}

export function getAgentSession(): Promise<AgentSnapshot> {
  return request<AgentSnapshot>('/api/agent');
}

export function sendAgentMessage(message: string, thinkingLevel: AgentThinkingLevel): Promise<AgentSnapshot> {
  return request<AgentSnapshot>('/api/agent/message', {
    method: 'POST',
    body: JSON.stringify({ message, thinking_level: thinkingLevel }),
  });
}

export function stopAgent(): Promise<AgentSnapshot> {
  return request<AgentSnapshot>('/api/agent/stop', { method: 'POST' });
}

export function resetAgent(): Promise<AgentSnapshot> {
  return request<AgentSnapshot>('/api/agent/reset', { method: 'POST' });
}

export function confirmAgentTool(confirmationId: string, approved: boolean): Promise<AgentSnapshot> {
  return request<AgentSnapshot>('/api/agent/confirm', {
    method: 'POST',
    body: JSON.stringify({ confirmation_id: confirmationId, approved }),
  });
}

export interface AgentSessionSummary {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
}

export function listAgentSessions(): Promise<{ sessions: AgentSessionSummary[] }> {
  return request<{ sessions: AgentSessionSummary[] }>('/api/agent/sessions');
}

export function openAgentSession(sessionId: string): Promise<AgentSnapshot> {
  return request<AgentSnapshot>(`/api/agent/sessions/${encodeURIComponent(sessionId)}/open`, {
    method: 'POST',
  });
}

export function deleteAgentSession(sessionId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}

export function getVersion(): Promise<VersionInfo> {
  return request<VersionInfo>('/api/version');
}

export function getUpdateState(): Promise<UpdateState> {
  return request<UpdateState>('/api/update');
}

export function checkUpdate(manual = true): Promise<UpdateState> {
  return request<UpdateState>('/api/update/check', {
    method: 'POST',
    body: JSON.stringify({ manual }),
  });
}

export function downloadUpdate(): Promise<UpdateState> {
  return request<UpdateState>('/api/update/download', { method: 'POST' });
}

export function cancelUpdateDownload(): Promise<UpdateState> {
  return request<UpdateState>('/api/update/cancel', { method: 'POST' });
}

export function installUpdate(): Promise<UpdateState> {
  return request<UpdateState>('/api/update/install', { method: 'POST' });
}

export function getChangelog(): Promise<ChangelogResponse> {
  return request<ChangelogResponse>('/api/update/changelog');
}

export function getSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>('/api/settings');
}

/** save=false：只改内存态，界面实时生效；落盘由 settings 页显式决定。 */
export function patchSettings(values: Record<string, unknown>, save = false): Promise<SettingsResponse> {
  return request<SettingsResponse>('/api/settings', {
    method: 'PATCH',
    body: JSON.stringify({ values, save }),
  });
}

export function getProject(): Promise<ProjectInfo> {
  return request<ProjectInfo>('/api/project');
}

export function setProjectPath(projectPath: string, gameFolder?: string): Promise<ProjectInfo> {
  return request<ProjectInfo>('/api/project/path', {
    method: 'POST',
    body: JSON.stringify({ project_path: projectPath, game_folder: gameFolder ?? null }),
  });
}

/**
 * 按目录解析 Ren'Py 项目身份（选输入目录时顺带绑定）。
 * 目录不含项目结构时后端返回 409，调用方应忽略并只保留 input_folder。
 */
export function resolveProject(path: string): Promise<ProjectInfo> {
  return request<ProjectInfo>('/api/project/resolve', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

// ---------- .rbox 工程文件 ----------

/** 只读校验 .rbox 元数据，不触碰缓存。 */
export function inspectProjectFile(path: string): Promise<ProjectFileDescription> {
  return request<ProjectFileDescription>('/api/project/file/inspect', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

/** 把当前输出缓存与白名单项目设置导出为 .rbox。 */
export function exportProjectFile(path: string): Promise<ProjectFileExportResult> {
  return request<ProjectFileExportResult>('/api/project/file/export', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

/** 严格预览用户显式选择的旧输出/cache 目录；不改当前工程绑定。 */
export function inspectLegacyProjectCache(folder: string): Promise<LegacyProjectCacheDescription> {
  return request<LegacyProjectCacheDescription>('/api/project/file/legacy/inspect', {
    method: 'POST',
    body: JSON.stringify({ folder }),
  });
}

/** 从指定旧缓存创建 .rbox，不替换源缓存或当前输出。 */
export function exportLegacyProjectFile(folder: string, path: string): Promise<LegacyProjectFileExportResult> {
  return request<LegacyProjectFileExportResult>('/api/project/file/legacy/export', {
    method: 'POST',
    body: JSON.stringify({ folder, path }),
  });
}

/**
 * 导入 .rbox：默认绑定模式（单文件工程，.rbox 直接作为工作缓存，不再复制
 * cache 副本）；`bind=false` 保持旧语义（内容复制进 <输出>/cache/）。
 */
export function importProjectFile(path: string, bind = true): Promise<ProjectFileImportResult> {
  return request<ProjectFileImportResult>('/api/project/file/import', {
    method: 'POST',
    body: JSON.stringify({ path, bind }),
  });
}

/**
 * 在输出目录创建一个新的 .rbox 并绑定为当前单文件工程（默认路径为
 * `<输出目录>/<项目名>.rbox`）。既有目录缓存会迁进文件；不覆盖已有文件。
 */
export function createProjectFile(path = ''): Promise<ProjectFileCreateResult> {
  return request<ProjectFileCreateResult>('/api/project/file/create', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

/** 当前单文件工程绑定状态：哪个 .rbox 在工作、是否还在原地、有无同步风险。 */
export function getProjectFileBinding(): Promise<ProjectFileBinding> {
  return request<ProjectFileBinding>('/api/project/file/binding');
}

/** 解除绑定：进度落回 <输出>/cache，工程文件留作只读快照。 */
export function unbindProjectFile(): Promise<ProjectFileBinding & { snapshot: string }> {
  return request<ProjectFileBinding & { snapshot: string }>('/api/project/file/unbind', { method: 'POST' });
}

export function listJobs(): Promise<JobSnapshot[]> {
  return request<{ jobs: JobSnapshot[] }>('/api/jobs').then((body) => body.jobs);
}

export function getJob(jobId: string): Promise<JobSnapshot> {
  return request<JobSnapshot>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function cancelJob(jobId: string): Promise<JobSnapshot> {
  return request<JobSnapshot>(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
}

// ---------- 术语表 ----------

export function syncGlossary(rows: GlossaryRow[]): Promise<GlossaryRows> {
  return request<GlossaryRows>('/api/glossary/sync', {
    method: 'POST',
    body: JSON.stringify({ kind: 'GLOSSARY', rows }),
  });
}

export function searchGlossary(
  rows: GlossaryRow[],
  keyword: string,
): Promise<{ index: number; total: number }> {
  return request('/api/glossary/search', {
    method: 'POST',
    body: JSON.stringify({ kind: 'GLOSSARY', rows, keyword, start: -1 }),
  });
}

export function loadGlossary(path: string, kind = 'GLOSSARY'): Promise<GlossaryRows> {
  return request<GlossaryRows>('/api/glossary/load', {
    method: 'POST',
    body: JSON.stringify({ path, kind }),
  });
}

export function saveGlossary(
  rows: GlossaryRow[],
  kind = 'GLOSSARY',
  path?: string,
  format: 'json' | 'xlsx' | 'both' = 'both',
): Promise<{ kind: string; path: string; total: number }> {
  return request('/api/glossary/save', {
    method: 'POST',
    body: JSON.stringify({ kind, rows, path: path ?? null, format }),
  });
}

// ---------- 翻译主流程 ----------

export function getTranslationState(): Promise<TranslationState> {
  return request<TranslationState>('/api/translation/state');
}

/**
 * 工具箱续跑探测：按 mode 推导输出目录，报告是否有可继续的翻译缓存。
 * 源码翻译停止后再次「开始」靠它区分「继续翻译」与「重新开始」。
 */
export function getSourceResumeInfo(inputFolder: string): Promise<TranslationResumableInfo> {
  const query = new URLSearchParams({ mode: 'source', input_folder: inputFolder });
  return request<TranslationResumableInfo>(`/api/translation/resumable?${query.toString()}`);
}

export function startTranslation(
  status: StartableProjectStatus,
  requestId?: string,
  preflightConfirmed = false,
  options?: TranslationStartOptions,
): Promise<TranslationStartResponse> {
  const opts = options ?? {};
  const body: Record<string, unknown> = {
    status,
    request_id: opts.requestId ?? requestId ?? null,
    preflight_confirmed: opts.preflightConfirmed ?? preflightConfirmed,
  };
  // 仅在显式带 mode 时附加工具箱字段，避免影响普通 start 契约。
  if (opts.mode) {
    body.mode = opts.mode;
    if (opts.project_key != null) body.project_key = opts.project_key;
    if (opts.game_path != null) body.game_path = opts.game_path;
    if (opts.tl_parent != null) body.tl_parent = opts.tl_parent;
    if (opts.tl_name != null) body.tl_name = opts.tl_name;
    if (opts.language != null) body.language = opts.language;
    if (opts.input_folder != null) body.input_folder = opts.input_folder;
    // source 输出由服务端推导；前端不再传可编辑 output_folder。
    if (opts.mode !== 'source' && opts.output_folder != null) body.output_folder = opts.output_folder;
    if (opts.source_language != null) body.source_language = opts.source_language;
    if (opts.target_language != null) body.target_language = opts.target_language;
    if (opts.traditional_chinese_enable != null) {
      body.traditional_chinese_enable = opts.traditional_chinese_enable;
    }
    if (opts.renpy_backup_original != null) body.renpy_backup_original = opts.renpy_backup_original;
    if (opts.auto_write_back != null) body.auto_write_back = opts.auto_write_back;
    if (opts.external_backup_dir != null) body.external_backup_dir = opts.external_backup_dir;
    if (opts.renpy_hook_incremental != null) body.renpy_hook_incremental = opts.renpy_hook_incremental;
    if (opts.generate_empty != null) body.generate_empty = opts.generate_empty;
  }
  return request<TranslationStartResponse>('/api/translation/start', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * 停止翻译。
 *
 * `projectKey` 是渲染端持有的当前 owner（来自 `/api/translation/state`）；
 * 后端有绑定项目时要求它精确匹配，用于拦住切项目后仍开着的旧页面。
 */
export function stopTranslation(projectKey?: string): Promise<{ ok: boolean; status: string }> {
  return request('/api/translation/stop', {
    method: 'POST',
    body: JSON.stringify({ project_key: projectKey ?? '' }),
  });
}

export function exportTranslation(projectKey?: string): Promise<{ ok: boolean }> {
  return request('/api/translation/export', {
    method: 'POST',
    body: JSON.stringify({ project_key: projectKey ?? '' }),
  });
}

export function reinjectTranslation(
  options: string | TranslationReinjectOptions,
): Promise<{ ok: boolean; output_folder: string }> {
  const body = typeof options === 'string'
    ? { output_folder: options }
    : options;
  return request('/api/translation/reinject', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function getHookTranslateStatus(
  projectKey?: string,
  requestId?: string,
): Promise<{
  project_key: string;
  job: JobSnapshot | null;
}> {
  const params = new URLSearchParams();
  if (projectKey) params.set('project_key', projectKey);
  if (requestId) params.set('request_id', requestId);
  const q = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/hook-translate/status${q}`);
}

export function startHookTranslate(
  options: HookTranslateStartOptions,
): Promise<HookTranslateStartResponse> {
  return request('/api/hook-translate/start', {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

export function stopHookTranslate(options?: {
  projectKey?: string;
  requestId?: string;
  runId?: number;
}): Promise<{ ok: boolean; stage?: string; job_id?: string }> {
  const params = new URLSearchParams();
  if (options?.projectKey) params.set('project_key', options.projectKey);
  if (options?.requestId) params.set('request_id', options.requestId);
  if (options?.runId) params.set('run_id', String(options.runId));
  const q = params.toString() ? `?${params.toString()}` : '';
  return request(`/api/hook-translate/stop${q}`, { method: 'POST' });
}

/** 只重置失败条目，不启动翻译；detail 兼容旧后端可能缺省。 */
export function retryFailedTranslations(
  projectKey?: string,
): Promise<{ ok: boolean; count: number; detail?: string }> {
  return request('/api/translation/retry-failed', {
    method: 'POST',
    body: JSON.stringify({ project_key: projectKey ?? '' }),
  });
}

export interface QualityReport {
  schema_version: number;
  failed_count: number;
  fallback_count: number;
  line_mismatch_count: number;
  error_type_counts: Record<string, number>;
  item_references: {
    item_index: number;
    reference: string;
    file_path: string;
    row: number;
    source_preview: string;
    status: string;
    retry_count: number;
    error_types: string[];
  }[];
}

export function getProofreadingQualityReport(): Promise<QualityReport> {
  return request<QualityReport>('/api/proofreading/report');
}

export function startProofreadingQuality(
  cacheToken: string,
  task: 'proofread' | 'polish',
  ids: number[],
): Promise<{ ok: boolean; accepted: number; skipped: number; task: string }> {
  return request('/api/proofreading/quality', {
    method: 'POST',
    body: JSON.stringify({ cache_token: cacheToken, task, ids }),
  });
}

export function cancelProofreadingQuality(): Promise<{ ok: boolean }> {
  return request('/api/proofreading/quality/cancel', { method: 'POST' });
}

export function estimateTokens(): Promise<TokenEstimate> {
  // 显式 {}：request() 固定带 application/json，无 body 时后端会 422 Field required。
  return request<TokenEstimate>('/api/translation/estimate', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

/** 整份剧情蓝图：章节、label 节点、真实进度与控制流。 */
export function getStoryBlueprint(): Promise<StoryBlueprintResponse> {
  return request<StoryBlueprintResponse>('/api/story-blueprint');
}

/** 项目体检：剧情蓝图能不能出图、卡在哪一步（未绑定 / 无 game / 已打包未解包 / 可出图）。 */
export function getStoryBlueprintReadiness(): Promise<StoryBlueprintReadiness> {
  return request<StoryBlueprintReadiness>('/api/story-blueprint/readiness');
}

/** 卡片缩略图地址：path 是 game/ 下的相对路径，安全校验在后端 asset 接口。 */
export function blueprintAssetUrl(path: string): string {
  return `${apiBase()}/api/story-blueprint/asset?path=${encodeURIComponent(path)}`;
}

/** 一个 label 的逐行明细：行号、说话人、原文、缓存译文与状态。 */
export function getStoryBlueprintLabel(
  chapter: string,
  id: string,
): Promise<StoryBlueprintLabelDetail> {
  const query = new URLSearchParams({ chapter, id });
  return request<StoryBlueprintLabelDetail>(`/api/story-blueprint/label?${query.toString()}`);
}

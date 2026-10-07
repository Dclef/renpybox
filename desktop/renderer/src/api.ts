/**
 * sidecar 业务接口客户端。
 *
 * 所有路由都对应 api/ 下真实存在的 FastAPI 路由；没有 mock 数据。
 * 后端 4xx/5xx 时把 detail 原文带出来 —— 界面直接显示它，
 * 不再自己编一套「出错了」文案把真实原因盖掉。
 */

import type {
  HealthInfo,
  JobSnapshot,
  ProjectInfo,
  SettingsResponse,
  StartableProjectStatus,
  TokenEstimate,
  TranslationStartResponse,
  TranslationState,
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
const SIDECAR_ORIGIN = 'http://127.0.0.1:9712';

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

export function getVersion(): Promise<VersionInfo> {
  return request<VersionInfo>('/api/version');
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

export function listJobs(): Promise<{ jobs: JobSnapshot[] }> {
  return request<{ jobs: JobSnapshot[] }>('/api/jobs');
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

export function startTranslation(
  status: StartableProjectStatus,
  requestId?: string,
  preflightConfirmed = false,
): Promise<TranslationStartResponse> {
  return request<TranslationStartResponse>('/api/translation/start', {
    method: 'POST',
    body: JSON.stringify({
      status,
      request_id: requestId ?? null,
      preflight_confirmed: preflightConfirmed,
    }),
  });
}

export function stopTranslation(): Promise<{ ok: boolean; status: string }> {
  return request('/api/translation/stop', { method: 'POST' });
}

export function exportTranslation(): Promise<{ ok: boolean }> {
  return request('/api/translation/export', { method: 'POST' });
}

export function retryFailedTranslations(): Promise<{ ok: boolean; count: number; detail: string }> {
  return request('/api/translation/retry-failed', { method: 'POST' });
}

export function estimateTokens(): Promise<TokenEstimate> {
  return request<TokenEstimate>('/api/translation/estimate', { method: 'POST' });
}

/**
 * sidecar 业务接口客户端（api 模式）。
 *
 * bench 模式（跑性能门禁用）没有这些路由，请求会 404；
 * 因此启动时先探 /health 拿 mode，再决定启用哪套 UI。
 */

export interface HealthInfo {
  ok: boolean;
  mode: 'api' | 'bench';
  app_version: string;
  python_version?: string;
  config_path?: string;
}

export interface SettingsResponse {
  values: Record<string, unknown>;
  masked: string[];
}

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} → ${res.status}`);
  }
  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('/health');
}

export function getSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>('/api/settings');
}

export function patchSettings(values: Record<string, unknown>): Promise<SettingsResponse> {
  return request<SettingsResponse>('/api/settings', {
    method: 'PATCH',
    body: JSON.stringify({ values, save: false }),
  });
}

/** 术语表去重：走真实的 module/TableManager.sync() */
export function syncGlossary(rows: GlossaryRow[]): Promise<GlossaryRows> {
  return request<GlossaryRows>('/api/glossary/sync', {
    method: 'POST',
    body: JSON.stringify({ kind: 'GLOSSARY', rows }),
  });
}

export function searchGlossary(rows: GlossaryRow[], keyword: string): Promise<{ index: number; total: number }> {
  return request('/api/glossary/search', {
    method: 'POST',
    body: JSON.stringify({ kind: 'GLOSSARY', rows, keyword, start: -1 }),
  });
}

export function getProject(): Promise<Record<string, string>> {
  return request('/api/project');
}

export function setProjectPath(projectPath: string, gameFolder?: string): Promise<Record<string, string>> {
  return request('/api/project/path', {
    method: 'POST',
    body: JSON.stringify({ project_path: projectPath, game_folder: gameFolder ?? null }),
  });
}

export const DEMO_ROWS: GlossaryRow[] = [
  { src: 'ソyma', dst: '沙发', info: '', regex: false, case_sensitive: false },
  { src: 'ソyma', dst: '', info: '', regex: false, case_sensitive: false },
  { src: 'おにぎり', dst: '饭团', info: '', regex: false, case_sensitive: false },
  { src: 'たけやき', dst: '烤竹轮', info: '', regex: false, case_sensitive: false },
];
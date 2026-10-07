import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from './api';
import type { HealthInfo } from './api';

/**
 * api 模式探针 + 真实接口调用。
 *
 * bench 模式（性能门禁）没有 /api 路由，这里会拿到 404 并自动降级，
 * 所以同一份渲染代码既能跑门禁也能连真实业务。
 */
export function useRenpyApi() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const logRef = useRef(0);

  const append = useCallback((line: string) => {
    setLog((prev) => [`${String(++logRef.current).padStart(2, '0')}  ${line}`, ...prev].slice(0, 12));
  }, []);

  useEffect(() => {
    let alive = true;
    api
      .getHealth()
      .then((info) => {
        if (!alive) return;
        setHealth(info);
        append(`sidecar 模式=${info.mode} 版本=${info.app_version} python=${info.python_version ?? '—'}`);
      })
      .catch(() => {
        if (alive) append('未连上 sidecar');
      });
    return () => {
      alive = false;
    };
  }, [append]);

  const run = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        const result = await fn();
        append(`${label}：${JSON.stringify(result).slice(0, 220)}`);
      } catch (err) {
        append(`${label} 失败：${String(err)}`);
      } finally {
        setBusy(false);
      }
    },
    [append],
  );

  const loadSettings = useCallback(
    () =>
      run('读取设置', async () => {
        const s = await api.getSettings();
        return {
          字段数: Object.keys(s.values).length,
          已脱敏: s.masked,
          theme: s.values.theme,
          app_language: s.values.app_language,
          token_threshold: s.values.token_threshold,
        };
      }),
    [run],
  );

  const switchTheme = useCallback(
    () =>
      run('切换主题设置', async () => {
        const s = await api.getSettings();
        const next = s.values.theme === 'LIGHT' ? 'DARK' : 'LIGHT';
        await api.patchSettings({ theme: next });
        return { theme: next };
      }),
    [run],
  );

  const dedupeGlossary = useCallback(
    () =>
      run('术语表去重（真实 TableManager）', async () => {
        const result = await api.syncGlossary(api.DEMO_ROWS);
        return { 去重前: api.DEMO_ROWS.length, 去重后: result.total, 保留: result.rows.map((r) => `${r.src}→${r.dst}`) };
      }),
    [run],
  );

  const searchGlossary = useCallback(
    () =>
      run('术语表搜索', async () => {
        const result = await api.searchGlossary(api.DEMO_ROWS, '饭团');
        return { 命中行: result.index };
      }),
    [run],
  );

  const readProject = useCallback(() => run('读取项目', () => api.getProject()), [run]);

  const isApi = health?.mode === 'api';

  return { health, isApi, log, busy, loadSettings, switchTheme, dedupeGlossary, searchGlossary, readProject };
}
/**
 * 应用级状态 —— 把「一份配置」和「一条事件流」收敛到一处。
 *
 * 关键约定：
 *   * 配置只有一份。所有页面读同一份 values，改动先本地生效再 PATCH，
 *     失败回滚。这样切页不会看到旧快照。
 *   * 事件只有一条 WS。useSidecarEvents 在这里被调用一次，
 *     TRANSLATION_START / STOP / DONE / UPDATE 直接驱动翻译页。
 *   * 翻译进度不在 React 之外另存一份。事件来了就合并进 translation 状态，
 *     由页面自己渲染。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import * as api from './api';
import type {
  HealthInfo,
  ProjectInfo,
  SettingsResponse,
  StartableProjectStatus,
  TokenEstimate,
  TranslationStartResponse,
  TranslationState,
  VersionInfo,
  JobSnapshot,
  WsEventMessage,
  WsJobMessage,
} from './types';
import { normalizeLang, type Lang } from './i18n';
import { persistTheme, readStoredTheme } from './theme';
import { useSidecarEvents } from './useSidecarEvents';

export type ThemeName = 'LIGHT' | 'DARK';

export interface Toast {
  id: number;
  tone: 'info' | 'success' | 'warning' | 'error';
  text: string;
}

export type LinkState = 'connecting' | 'open' | 'closed';

export interface AppState {
  ready: boolean;
  /** 启动时读取一次的界面语言。运行中修改语言不会改变界面，重启后生效。 */
  bootLanguage: Lang | null;
  jobs: JobSnapshot[];
  health: HealthInfo | null;
  version: VersionInfo | null;
  project: ProjectInfo | null;
  theme: ThemeName;
  settings: SettingsResponse | null;
  translation: TranslationState;
  /** 翻译定时器跨页面保留；项目键用于避免切换项目后误触发。 */
  translationTimerDeadline: number | null;
  translationTimerProjectKey: string;
  /** PATCH 进行中，避免同一字段连点造成乱序写入 */
  saving: boolean;
  /** WS 连接状态，侧边栏底部的状态点用它 */
  link: LinkState;
  toasts: Toast[];
  reloadSettings: () => Promise<void>;
  reloadProject: () => Promise<void>;
  reloadTranslation: () => Promise<void>;
  setTheme: (theme: ThemeName) => void;
  setSetting: (key: string, value: unknown) => Promise<boolean>;
  saveSettings: (values: Record<string, unknown>) => Promise<boolean>;
  setProjectPath: (projectPath: string, gameFolder?: string) => Promise<void>;
  startTranslation: (
    status: StartableProjectStatus,
    preflightConfirmed?: boolean,
  ) => Promise<TranslationStartResponse>;
  stopTranslation: () => Promise<void>;
  setTranslationTimer: (deadline: number | null, projectKey?: string) => void;
  exportTranslation: () => Promise<void>;
  retryFailedTranslations: () => Promise<void>;
  estimateTokens: () => Promise<TokenEstimate | null>;
  pushToast: (tone: Toast['tone'], text: string) => void;
  dismissToast: (id: number) => void;
  /** 供页面订阅原始事件（例如专家设置里跟随项目变更刷新） */
  subscribe: (handler: (event: WsEventMessage) => void) => () => void;
}

const EMPTY_TRANSLATION: TranslationState = {
  engine_status: 'IDLE',
  stop_barrier: false,
  single_tasks: false,
  request_id: '',
  run_id: 0,
  running: { running: 0, max: 0 },
  progress: {},
  active_output_folder: '',
};

let toastSeq = 0;

export function useAppState(): AppState {
  const [ready, setReady] = useState(false);
  const [bootLanguage, setBootLanguage] = useState<Lang | null>(null);
  const [jobs, setJobs] = useState<JobSnapshot[]>([]);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [translation, setTranslation] = useState<TranslationState>(EMPTY_TRANSLATION);
  const [translationTimerDeadline, setTranslationTimerDeadline] = useState<number | null>(null);
  const [translationTimerProjectKey, setTranslationTimerProjectKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [link, setLink] = useState<LinkState>('connecting');
  // 服务端设置返回前用本地缓存的主题兜底，避免启动时先黑后白。
  const [fallbackTheme] = useState<ThemeName>(readStoredTheme);

  // 用 ref 兜住回调闭包：WS 回调注册一次，里面的 setState 必须看到最新值。
  const latest = useRef({ settings, project, translation, translationTimerProjectKey });
  latest.current = { settings, project, translation, translationTimerProjectKey };

  const handlers = useRef(new Set<(event: WsEventMessage) => void>());
  const pushToast = useCallback((tone: Toast['tone'], text: string) => {
    if (!text) return;
    const id = ++toastSeq;
    setToasts((prev) => [...prev, { id, tone, text }].slice(-4));
  }, []);
  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const subscribe = useCallback((handler: (event: WsEventMessage) => void) => {
    handlers.current.add(handler);
    return () => {
      handlers.current.delete(handler);
    };
  }, []);

  const reloadSettings = useCallback(async () => {
    const next = await api.getSettings();
    setSettings(next);
  }, []);

  const reloadProject = useCallback(async () => {
    setProject(await api.getProject());
  }, []);

  const translationRequest = useRef(0);
  const reloadTranslation = useCallback(async () => {
    const request = ++translationRequest.current;
    const next = await api.getTranslationState();
    // HTTP 返回完整快照；新项目的空进度也必须覆盖旧项目，迟到响应不能回滚状态。
    if (request === translationRequest.current) setTranslation(next);
  }, []);

  const saveSettings = useCallback(
    async (values: Record<string, unknown>) => {
      setSettings((prev) => prev ? { ...prev, values: { ...prev.values, ...values } } : prev);
      setSaving(true);
      try {
        const next = await api.patchSettings(values, true);
        setSettings(next);
        if (Object.keys(values).some((key) => ['input_folder', 'output_folder', 'renpy_project_path', 'renpy_tl_folder'].includes(key))) {
          await reloadTranslation();
        }
        return true;
      } catch (error) {
        pushToast('error', '保存设置失败：' + (error instanceof Error ? error.message : String(error)));
        await api.getSettings().then(setSettings).catch(() => {});
        return false;
      } finally {
        setSaving(false);
      }
    },
    [pushToast, reloadTranslation],
  );

  const setSetting = useCallback((key: string, value: unknown) => saveSettings({ [key]: value }), [saveSettings]);

  const setTranslationTimer = useCallback((deadline: number | null, projectKey = '') => {
    setTranslationTimerDeadline(deadline);
    setTranslationTimerProjectKey(deadline === null ? '' : projectKey);
  }, []);

  const setProjectPath = useCallback(
    async (projectPath: string, gameFolder?: string) => {
      setTranslationTimer(null);
      const next = await api.setProjectPath(projectPath, gameFolder);
      setProject(next);
      await Promise.all([reloadSettings(), reloadTranslation()]);
    },
    [reloadSettings, reloadTranslation, setTranslationTimer],
  );

  const startTranslation = useCallback(
    async (status: StartableProjectStatus, preflightConfirmed = false) => {
      // 手动开始或定时开始后都不能保留旧的截止时间。
      setTranslationTimer(null);
      const response = await api.startTranslation(status, undefined, preflightConfirmed);
      if (response.accepted) {
        await reloadTranslation();
      } else if (response.reason !== 'ASSETS_MISSING') {
        // ASSETS_MISSING 由翻译页弹窗处理（去工作台 or 仍然继续），
        // 这里再弹一次 toast 只会和弹窗抢注意力。
        pushToast('warning', response.detail || '任务正在执行中，请稍后再试 …');
      }
      return response;
    },
    [pushToast, reloadTranslation, setTranslationTimer],
  );

  const stopTranslation = useCallback(async () => {
    setTranslationTimer(null);
    await api.stopTranslation();
    await reloadTranslation();
  }, [reloadTranslation, setTranslationTimer]);

  // 定时器属于应用状态，切页后仍运行，到点只消费一次并尝试启动任务。
  useEffect(() => {
    if (translationTimerDeadline === null) return;
    const tick = () => {
      if (Date.now() < translationTimerDeadline) return;
      setTranslationTimer(null);
      const current = latest.current;
      const currentProjectKey = `${current.project?.renpy_project_path ?? ''}\n${String(current.settings?.values.input_folder ?? '')}`;
      if (
        !current.settings
        || current.translation.engine_status !== 'IDLE'
        || current.translation.stop_barrier
        || current.translation.single_tasks
        || (current.translationTimerProjectKey && current.translationTimerProjectKey !== currentProjectKey)
      ) {
        pushToast('warning', '定时翻译已跳过：项目已切换或当前任务不可开始');
        return;
      }
      void startTranslation('UNTRANSLATED')
        .then((response) => {
          if (!response.accepted && response.reason === 'ASSETS_MISSING') {
            pushToast('warning', response.detail || '定时翻译未启动：当前项目没有可用资产');
          }
        })
        .catch((error: unknown) => pushToast('error', error instanceof Error ? error.message : String(error)));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [pushToast, setTranslationTimer, startTranslation, translationTimerDeadline]);

  const exportTranslation = useCallback(async () => {
    await api.exportTranslation();
  }, []);

  const retryFailedTranslations = useCallback(async () => {
    const result = await api.retryFailedTranslations();
    const count = Number(result.count ?? 0);
    // 后端已按缓存重算进度，刷新快照让「可继续」与已译/待译/失败统计立即生效。
    await reloadTranslation();
    pushToast(
      count > 0 ? 'success' : 'info',
      count > 0
        ? `已重置 ${count} 条失败项，请点击「继续任务」重新翻译`
        : result.detail || '没有找到需要重翻的失败项',
    );
  }, [pushToast, reloadTranslation]);

  const estimateTokens = useCallback(async () => {
    const result = await api.estimateTokens();
    return result;
  }, []);

  const setTheme = useCallback((theme: ThemeName) => {
    persistTheme(theme);
    setSettings((prev) => {
      if (!prev) return prev;
      return { ...prev, values: { ...prev.values, theme } };
    });
    void api.patchSettings({ theme }, true);
  }, []);

  // 启动：并行读取健康、版本、项目、配置、翻译状态。
  useEffect(() => {
    if (link === 'closed') { setReady(true); return; }
    let alive = true;
    const boot = async () => {
      const request = ++translationRequest.current;
      try {
        const [healthInfo, versionInfo, projectInfo, settingsInfo, translationState] = await Promise.all([
          api.getHealth(),
          api.getVersion(),
          api.getProject(),
          api.getSettings(),
          api.getTranslationState(),
        ]);
        if (!alive) return;
        setHealth(healthInfo);
        setVersion(versionInfo);
        setProject(projectInfo);
        setSettings(settingsInfo);
        if (request === translationRequest.current) setTranslation(translationState);
        setReady(true);
      } catch (error) {
        if (!alive) return;
        if (link === 'open') pushToast('error', `连接后端失败：${error instanceof Error ? error.message : String(error)}`);
        setReady(true);
      }
    };
    void boot();
    return () => {
      alive = false;
    };
  }, [pushToast, link]);

  useEffect(() => {
    if (!ready || bootLanguage !== null) return;
    setBootLanguage(normalizeLang(settings?.values.app_language));
  }, [ready, bootLanguage, settings]);

  const upsertJob = useCallback((job: JobSnapshot) => {
    const summary = { ...job };
    delete summary.result;
    setJobs((prev) => {
      const next = [summary, ...prev.filter((item) => item.id !== job.id)];
      while (next.length > 64) {
        let removed = false;
        for (let index = next.length - 1; index >= 0; index -= 1) {
          const status = next[index]?.status;
          if (status === 'done' || status === 'failed' || status === 'cancelled') {
            next.splice(index, 1);
            removed = true;
            break;
          }
        }
        if (!removed) break;
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (link !== 'open') return;
    let alive = true;
    void api.listJobs()
      .then((listed) => {
        if (!alive) return;
        setJobs(listed.map((job) => {
          const summary = { ...job };
          delete summary.result;
          return summary;
        }));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [link]);

  useSidecarEvents(
    useCallback((message: WsEventMessage) => {
      if (message.type === 'event') {
        switch (message.event) {
          case 'PROJECT_CHANGED':
          case 'PROJECT_STATUS':
            if (message.event === 'PROJECT_CHANGED') setTranslationTimer(null);
            void Promise.all([reloadProject(), reloadSettings(), reloadTranslation()]).catch((error) => pushToast('error', String(error)));
            break;
          case 'GLOSSARY_REFRESH':
            pushToast('info', '术语表已更新');
            break;
          case 'APP_TOAST_SHOW': {
            const data = message.data as { content?: string; message?: string; type?: string } | undefined;
            const text = typeof data?.content === 'string' ? data.content : typeof data?.message === 'string' ? data.message : '';
            const tone =
              data?.type === 'ERROR'
                ? 'error'
                : data?.type === 'SUCCESS'
                  ? 'success'
                  : data?.type === 'WARNING'
                    ? 'warning'
                    : 'info';
            pushToast(tone, text);
            break;
          }
          case 'PLATFORM_TEST_DONE':
          case 'TRANSLATION_START_RESULT':
            void reloadTranslation();
            break;
          case 'TRANSLATION_DONE':
            void reloadTranslation();
            break;
          case 'TRANSLATION_STOP':
            setTranslationTimer(null);
            void reloadTranslation();
            break;
          case 'PROJECT_STATUS_CHECK_DONE':
            void reloadTranslation();
            break;
          case 'TRANSLATION_UPDATE': {
            translationRequest.current += 1;
            const nested = message.data.progress;
            const progress = nested && typeof nested === 'object' ? nested : message.data;
            setTranslation((prev) => ({ ...prev, progress: { ...prev.progress, ...progress } }));
            break;
          }
          case 'TRANSLATION_START':
            setTranslationTimer(null);
            setTranslation((prev) => ({ ...prev, progress: {} }));
            void reloadTranslation();
            break;
          default:
            break;
        }
        handlers.current.forEach((handler) => handler(message));
      }
    }, [pushToast, reloadProject, reloadSettings, reloadTranslation, setTranslationTimer]),
    setLink,
    useCallback((message: WsJobMessage) => upsertJob(message.job), [upsertJob]),
  );

  // 服务端 settings.theme 是最终真实值；未返回或值无效时沿用本地兜底。
  const theme = useMemo<ThemeName>(() => {
    const stored = settings?.values.theme;
    return stored === 'LIGHT' || stored === 'DARK' ? stored : fallbackTheme;
  }, [settings?.values.theme, fallbackTheme]);

  // 服务端值落地后同步到本地缓存，下次启动首帧即与真实设置一致。
  useEffect(() => {
    const stored = settings?.values.theme;
    if (stored === 'LIGHT' || stored === 'DARK') persistTheme(stored);
  }, [settings?.values.theme]);

  return {
    ready,
    bootLanguage,
    jobs,
    health,
    version,
    project,
    theme,
    settings,
    translation,
    translationTimerDeadline,
    translationTimerProjectKey,
    saving,
    link,
    toasts,
    reloadSettings,
    reloadProject,
    reloadTranslation,
    setTheme,
    setSetting,
    saveSettings,
    setProjectPath,
    startTranslation,
    stopTranslation,
    setTranslationTimer,
    exportTranslation,
    retryFailedTranslations,
    estimateTokens,
    pushToast,
    dismissToast,
    subscribe,
  };
}

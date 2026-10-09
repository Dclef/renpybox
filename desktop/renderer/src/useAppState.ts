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
  /** PATCH 进行中，避免同一字段连点造成乱序写入 */
  saving: boolean;
  /** WS 连接状态，侧边栏底部的状态点用它 */
  link: LinkState;
  toasts: Toast[];
  reloadSettings: () => Promise<void>;
  reloadProject: () => Promise<void>;
  reloadTranslation: () => Promise<void>;
  setTheme: (theme: ThemeName) => void;
  setSetting: (key: string, value: unknown) => void;
  setProjectPath: (projectPath: string, gameFolder?: string) => Promise<void>;
  startTranslation: (
    status: StartableProjectStatus,
    preflightConfirmed?: boolean,
  ) => Promise<TranslationStartResponse>;
  stopTranslation: () => Promise<void>;
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
  const [saving, setSaving] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [link, setLink] = useState<LinkState>('connecting');

  // 用 ref 兜住回调闭包：WS 回调注册一次，里面的 setState 必须看到最新值。
  const latest = useRef({ settings, project, translation });
  latest.current = { settings, project, translation };

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

  const reloadTranslation = useCallback(async () => {
    const next = await api.getTranslationState();
    setTranslation((prev) => ({ ...next, progress: { ...prev.progress, ...next.progress } }));
  }, []);

  const setSetting = useCallback(
    (key: string, value: unknown) => {
      setSettings((prev) => {
        if (!prev) return prev;
        return { ...prev, values: { ...prev.values, [key]: value } };
      });
      setSaving(true);
      api
        .patchSettings({ [key]: value }, true)
        .then((next) => setSettings((prev) => (prev ? { ...prev, ...next } : prev)))
        .catch((error: unknown) => {
          const text = error instanceof Error ? error.message : String(error);
          pushToast('error', `保存设置失败：${text}`);
          // 回滚到服务端真实值，否则界面停在未落盘的状态上
          void api.getSettings().then((fresh) => setSettings(fresh));
        })
        .finally(() => setSaving(false));
    },
    [pushToast],
  );

  const setProjectPath = useCallback(
    async (projectPath: string, gameFolder?: string) => {
      const next = await api.setProjectPath(projectPath, gameFolder);
      setProject(next);
    },
    [],
  );

  const startTranslation = useCallback(
    async (status: StartableProjectStatus, preflightConfirmed = false) => {
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
    [pushToast, reloadTranslation],
  );

  const stopTranslation = useCallback(async () => {
    await api.stopTranslation();
    await reloadTranslation();
  }, [reloadTranslation]);

  const exportTranslation = useCallback(async () => {
    await api.exportTranslation();
  }, []);

  const retryFailedTranslations = useCallback(async () => {
    const result = await api.retryFailedTranslations();
    pushToast(result.count > 0 ? 'success' : 'info', result.detail);
  }, [pushToast]);

  const estimateTokens = useCallback(async () => {
    const result = await api.estimateTokens();
    return result;
  }, []);

  const setTheme = useCallback((theme: ThemeName) => {
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
        setTranslation(translationState);
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

  // 项目被侧边栏之外的地方改动（工具箱、Agent）时，同步标题栏与项目页。
  useEffect(() => {
    return subscribe((event) => {
      if (event.event === 'PROJECT_CHANGED' || event.event === 'PROJECT_STATUS') {
        void reloadProject();
      }
    });
  }, [subscribe, reloadProject]);

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
            void reloadProject();
            break;
          case 'GLOSSARY_REFRESH':
            pushToast('info', '术语表已更新');
            break;
          case 'APP_TOAST_SHOW': {
            const data = message.data as { content?: string; type?: string } | undefined;
            const text = typeof data?.content === 'string' ? data.content : '';
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
            void reloadTranslation();
            break;
          case 'TRANSLATION_UPDATE':
          case 'PROJECT_STATUS_CHECK_DONE':
            // 共享进度快照在应用级保留，切换页面和任务完成后仍可查看统计。
            setTranslation((prev) => ({ ...prev, progress: { ...prev.progress, ...message.data } }));
            break;
          case 'TRANSLATION_START':
            setTranslation((prev) => ({ ...prev, progress: {} }));
            void reloadTranslation();
            break;
          default:
            break;
        }
        handlers.current.forEach((handler) => handler(message));
      }
    }, [pushToast, reloadProject, reloadTranslation]),
    setLink,
    useCallback((message: WsJobMessage) => upsertJob(message.job), [upsertJob]),
  );

  const theme = useMemo<ThemeName>(() => {
    const stored = settings?.values.theme;
    return stored === 'LIGHT' ? 'LIGHT' : 'DARK';
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
    saving,
    link,
    toasts,
    reloadSettings,
    reloadProject,
    reloadTranslation,
    setTheme,
    setSetting,
    setProjectPath,
    startTranslation,
    stopTranslation,
    exportTranslation,
    retryFailedTranslations,
    estimateTokens,
    pushToast,
    dismissToast,
    subscribe,
  };
}

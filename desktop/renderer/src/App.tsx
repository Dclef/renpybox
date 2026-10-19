/**
 * 应用外壳：负责无边框窗口标题栏、主导航和页面切换。
 *
 * 业务页面继续复用现有 sidecar 状态与 API；壳层只维护布局，视觉令牌、
 * 交互状态和响应式细节集中在 styles.css。
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Alert, Tooltip } from 'antd';
import { ChevronDown, FileText, Folder, Moon, Sun } from 'lucide-react';

import {
  IconChromeClose,
  IconChromeMaximize,
  IconChromeMinimize,
  IconChromeRestore,
  NAV_ICONS,
} from './icons';
import { ErrorBoundary } from './components/ErrorBoundary';
import { UpdateNotice } from './components/UpdateNotice';
import { ToolPageFrame } from './components/ToolPageFrame';
import { APP_SETTINGS_NAV, findNavItem, isNavCurrent, NAV_SECTIONS, type PageKey } from './nav';
import { TOOL_SPECS } from './tools';
import type { TextKey } from './i18n';
import { ProjectPage } from './pages/ProjectPage';
import { SettingsPage } from './pages/SettingsPage';
import { PlatformPage } from './pages/PlatformPage';
import { CustomPromptPage } from './pages/CustomPromptPage';
import { AgentPage } from './pages/AgentPage';
import { ToolBoxPage } from './pages/ToolBoxPage';
import { TranslationPage } from './pages/TranslationPage';
import { WorkbenchPage } from './pages/WorkbenchPage';
import { ProofreadingPage } from './pages/ProofreadingPage';
import { GlossaryPage } from './pages/GlossaryPage';
import { PreservePage } from './pages/PreservePage';
import { HonorificPage } from './pages/HonorificPage';
import { OneKeyTranslatePage } from './pages/OneKeyTranslatePage';
import { PackUnpackPage } from './pages/PackUnpackPage';
import { MaSuitePage } from './pages/MaSuitePage';
import { BatchCorrectionPage } from './pages/BatchCorrectionPage';
import { NameExtractionPage } from './pages/NameExtractionPage';
import { DirectRpyTranslatePage } from './pages/DirectRpyTranslatePage';
import { SourceTranslatePage } from './pages/SourceTranslatePage';
import { HookTranslatePage } from './pages/HookTranslatePage';
import { HookSupplementPage } from './pages/HookSupplementPage';
import { FontReplacePage } from './pages/FontReplacePage';
import { RpyExtractionPage } from './pages/RpyExtractionPage';
import { ExtractToTlPage } from './pages/ExtractToTlPage';
import { ExtractJsonPage } from './pages/ExtractJsonPage';
import { AddLanguagePage } from './pages/AddLanguagePage';
import { SetDefaultLanguagePage } from './pages/SetDefaultLanguagePage';
import { ErrorRepairPage } from './pages/ErrorRepairPage';
import { TranslationReusePage } from './pages/TranslationReusePage';
import { AndroidBuildPage } from './pages/AndroidBuildPage';
import { HtmlImportPage } from './pages/HtmlImportPage';
import { GameModPage } from './pages/GameModPage';
import * as api from './api';
import { createT, I18nContext } from './i18n';
import { Dialog, Empty } from './ui';
import type { AppState } from './useAppState';
import type { DesktopAppInfo } from './preload';

const TOAST_TYPE = { info: 'info', success: 'success', warning: 'warning', error: 'error' } as const;

// 对齐 Qt AppFluentWindow 启动约 3s 自动检查更新：模块级防重，StrictMode 双挂载或重渲染只发一次
let webStartupUpdateCheckFired = false;

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  );
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => setMatches(media.matches);
    onChange();
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

type ToolPageKey = 'proofreading' | 'glossary' | 'preserve' | 'honorific' | 'onekey' | 'onekey-apply' | 'pack-unpack' | 'ma-suite' | 'batch-correction' | 'name-extraction' | 'direct-rpy-translate' | 'source-translate' | 'hook-translate' | 'hook-supplement' | 'font-replace' | 'rpy-extraction' | 'extract-to-tl' | 'extract-json' | 'add-language' | 'set-default-language' | 'error-repair' | 'translation-reuse' | 'android-build' | 'html-import' | 'game-mod';
const TOOL_PAGE_TOOL_KEY: Record<ToolPageKey, string> = {
  proofreading: 'proofreading',
  glossary: 'local_glossary',
  preserve: 'text_preserve',
  honorific: 'honorific_placeholder',
  onekey: 'one_key_translate',
  'onekey-apply': 'apply_translation',
  'pack-unpack': 'pack_unpack',
  'ma-suite': 'ma_suite',
  'batch-correction': 'batch_correction',
  'name-extraction': 'name_extraction',
  'direct-rpy-translate': 'direct_rpy_translate',
  'source-translate': 'source_translate',
  'hook-translate': 'hook_translate',
  'hook-supplement': 'hook_supplement',
  'font-replace': 'font_replace',
  'rpy-extraction': 'rpy_extraction_settings',
  'extract-to-tl': 'extract_to_tl',
  'extract-json': 'extract_json',
  'add-language': 'add_language',
  'set-default-language': 'set_default_language',
  'error-repair': 'error_repair',
  'translation-reuse': 'translation_reuse',
  'android-build': 'android_build',
  'html-import': 'html_import',
  'game-mod': 'game_mod',
};
const TOOL_PAGE_DESC: Record<ToolPageKey, TextKey> = {
  proofreading: 'app_tool_desc_proofreading',
  glossary: 'app_tool_desc_glossary',
  preserve: 'app_tool_desc_preserve',
  honorific: 'app_tool_desc_honorific',
  onekey: 'app_tool_desc_onekey',
  'onekey-apply': 'app_tool_desc_onekey_apply',
  'pack-unpack': 'app_tool_desc_pack_unpack',
  'ma-suite': 'app_tool_desc_ma_suite',
  'batch-correction': 'app_tool_desc_batch_correction',
  'name-extraction': 'app_tool_desc_name_extraction',
  'direct-rpy-translate': 'app_tool_desc_direct_rpy_translate',
  'source-translate': 'app_tool_desc_source_translate',
  'hook-translate': 'app_tool_desc_hook_translate',
  'hook-supplement': 'app_tool_desc_hook_supplement',
  'font-replace': 'app_tool_desc_font_replace',
  'rpy-extraction': 'app_tool_desc_rpy_extraction',
  'extract-to-tl': 'app_tool_desc_extract_to_tl',
  'extract-json': 'app_tool_desc_extract_json',
  'add-language': 'app_tool_desc_add_language',
  'set-default-language': 'app_tool_desc_set_default_language',
  'error-repair': 'app_tool_desc_error_repair',
  'translation-reuse': 'app_tool_desc_translation_reuse',
  'android-build': 'app_tool_desc_android_build',
  'html-import': 'app_tool_desc_html_import',
  'game-mod': 'app_tool_desc_game_mod',
};

// 警告与错误需要更长阅读时间，其余提示短暂停留即可。
const TOAST_DURATION_MS: Record<AppState['toasts'][number]['tone'], number> = {
  info: 3500,
  success: 3500,
  warning: 6000,
  error: 6000,
};

function ToastItem(props: { toast: AppState['toasts'][number]; onDismiss: (id: number) => void }) {
  const { toast, onDismiss } = props;
  // 每条提示各自持有计时器，卸载或 id 变化时清理，避免关闭已被替换的提示。
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_MS[toast.tone]);
    return () => clearTimeout(timer);
  }, [toast.id, toast.tone, onDismiss]);
  return (
    <Alert
      data-rb-toast=""
      type={TOAST_TYPE[toast.tone]}
      title={toast.text}
      closable={{ 'aria-label': '知道了', onClose: () => onDismiss(toast.id) }}
    />
  );
}

function Toasts(props: { toasts: AppState['toasts']; onDismiss: (id: number) => void }) {
  const { toasts, onDismiss } = props;
  if (toasts.length === 0) return null;
  return (
    <div className="rb-toasts">
      {toasts.map((toast) => <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />)}
    </div>
  );
}

export function App(props: { state: AppState; link: 'connecting' | 'open' | 'closed' }) {
  const { state, link } = props;
  const [active, setActive] = useState<PageKey>('translation');
  const [maximized, setMaximized] = useState(false);
  const [desktopInfo, setDesktopInfo] = useState<DesktopAppInfo | null>(null);
  const [dirty, setDirty] = useState(false);
  const allowClose = useRef(false);
  /** RPY 页关页/切换前取消并等待后台 worker 真正结束 */
  const rpyLeaveGuardRef = useRef<(() => Promise<void>) | null>(null);
  /** RPY 后台仍在收尾时阻止原生关闭绕过 guard */
  const rpyLeaveBlockedRef = useRef(false);
  const [pendingPage, setPendingPage] = useState<PageKey | 'close' | null>(null);
  const [exitConfirm, setExitConfirm] = useState(false);
  const closeRequestedRef = useRef<() => void>(() => {});
  const closeInFlight = useRef(false);

  const leaveRpyIfNeeded = async (): Promise<boolean> => {
    if (active !== 'rpy-extraction') return true;
    // A dirty editor is independent from the background worker.  Do not enter
    // the asynchronous cancel/poll guard for an ordinary draft-only change;
    // that guard is reserved for an actually running RPY job.
    if (!rpyLeaveBlockedRef.current) return true;
    try {
      await rpyLeaveGuardRef.current?.();
      return true;
    } catch {
      return false;
    }
  };

  const navigate = (page: PageKey | 'close') => {
    if (page === active) return;
    if (dirty) { setPendingPage(page); return; }
    if (page === 'close') { setExitConfirm(true); return; }
    // dirty=false 也必须走同一 RPY guard；失败留在本页
    void (async () => {
      if (!(await leaveRpyIfNeeded())) return;
      setActive(page);
    })();
  };

  closeRequestedRef.current = () => navigate('close');
  useEffect(() => window.renpy?.onCloseRequested?.(() => closeRequestedRef.current()), []);
  useEffect(() => {
    if (state.bootLanguage) window.renpy?.setLocale?.(state.bootLanguage);
  }, [state.bootLanguage]);

  // 系统关闭：未保存或 RPY worker 收尾中都不能直接放行。
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (allowClose.current) return;
      const rpyBlocked = active === 'rpy-extraction' && rpyLeaveBlockedRef.current;
      if (!dirty && !rpyBlocked) return;
      event.preventDefault(); event.returnValue = '';
      if (dirty) setPendingPage('close');
      else if (rpyBlocked) {
        void (async () => {
          if (await leaveRpyIfNeeded()) {
            allowClose.current = true;
            if (window.renpy?.closeConfirmed) window.renpy.closeConfirmed();
            else window.renpy?.close?.();
          }
        })();
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty, active]);

  // 仅网页端：启动约 3s 后静默检查更新（manual=false 不弹 toast）；Electron 由主进程自行处理。
  useEffect(() => {
    if (window.renpy) return;
    if (webStartupUpdateCheckFired) return;
    const timer = window.setTimeout(() => {
      if (webStartupUpdateCheckFired) return;
      webStartupUpdateCheckFired = true;
      void api.checkUpdate(false).catch(() => {
        /* 失败静默；结果由设置页的 APP_UPDATE_* 订阅刷新 */
      });
    }, 3000);
    return () => window.clearTimeout(timer);
  }, []);

  // 无边框窗口：最大化状态由主进程回推，标题栏的按钮图标要对上。
  useEffect(() => {
    return window.renpy?.onMaximizeChange?.(setMaximized);
  }, []);

  useEffect(() => {
    const bridge = window.renpy;
    if (!bridge) return;
    let active = true;
    void bridge.appInfo()
      .then((info) => { if (active) setDesktopInfo(info); })
      .catch((error) => { if (active) state.pushToast('error', `读取桌面信息失败：${String(error?.message || error)}`); });
    return () => { active = false; };
  }, [state.pushToast]);

  const t = useMemo(() => createT(state.bootLanguage ?? 'ZH'), [state.bootLanguage]);
  const linkText: Record<'connecting' | 'open' | 'closed', string> = {
    connecting: t('app_link_connecting'),
    open: t('app_link_open'),
    closed: t('app_link_closed'),
  };
  const expertMode = state.settings?.values.expert_mode === true;
  const sections = NAV_SECTIONS
    .map((section) => section.filter((item) => item.key !== 'expert-settings' || expertMode))
    .filter((section) => section.length > 0);
  const hasProject = Boolean(state.project?.renpy_project_path);
  const toolPage = (key: ToolPageKey, child: ReactNode) => {
    const requiresProject = TOOL_SPECS.find((item) => item.key === TOOL_PAGE_TOOL_KEY[key])?.requiresProject === true;
    return (
      <ToolPageFrame
        title={t(findNavItem(key).labelKey)}
        description={t(TOOL_PAGE_DESC[key])}
        blocked={requiresProject && !hasProject}
        onBack={() => navigate('toolbox')}
        onOpenProject={() => navigate('project')}
      >
        {child}
      </ToolPageFrame>
    );
  };
  const collapsed = useMediaQuery('(max-width: 999px)');
  const version = window.renpy ? desktopInfo?.appVersion ?? '' : state.version?.app_version ?? '';
  const showDesktopRecovery = Boolean(window.renpy) && desktopInfo?.packaged !== false;
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const projectName = projectPath.split(/[\\/]/).filter(Boolean).at(-1) || t('app_project_unbound_name');

  // 翻译页 preflight 判定缺资产时，让用户能直接跳到工作台补齐，
  // 不必自己找侧边栏（对齐 TranslationPage._open_workbench）。
  const [workbenchRequested, setWorkbenchRequested] = useState(0);
  // 页面渲染异常后的重挂计数：让「重试这一页」重新取数而不是复用坏状态。
  const [pageRetry, setPageRetry] = useState(0);
  useEffect(() => {
    if (workbenchRequested > 0) {
      setActive('workbench');
      setWorkbenchRequested(0);
    }
  }, [workbenchRequested]);

  useEffect(() => {
    if (!expertMode && active === 'expert-settings') navigate('basic-settings');
  }, [expertMode, active]);

  const body = (() => {
    switch (active) {
      case 'translation':
        return (
          <TranslationPage
            state={state}
            onOpenWorkbench={() => setWorkbenchRequested((n) => n + 1)}
            onOpenProofreading={() => navigate('proofreading')}
            onOpenProject={() => navigate('project')}
            onOpenPlatform={() => navigate('platform')}
          />
        );
      case 'proofreading':
        return toolPage('proofreading', <ProofreadingPage state={state} onDirtyChange={setDirty} embedded />);
      case 'glossary':
        return toolPage('glossary', <GlossaryPage state={state} onDirtyChange={setDirty} onNextStep={() => navigate('preserve')} embedded />);
      case 'preserve':
        return toolPage('preserve', <PreservePage state={state} onDirtyChange={setDirty} onNextStep={() => navigate('honorific')} />);
      case 'honorific':
        return toolPage('honorific', <HonorificPage state={state} onDirtyChange={setDirty} onNextStep={() => navigate('onekey')} />);
      case 'onekey':
        return toolPage('onekey', (
          <OneKeyTranslatePage
            state={state}
            onOpenTranslation={() => navigate('translation')}
            onOpenWorkbench={() => navigate('workbench')}
            onOpenGlossary={() => navigate('glossary')}
            onOpenPreserve={() => navigate('preserve')}
          />
        ));
      case 'onekey-apply':
        return toolPage('onekey-apply', (
          <OneKeyTranslatePage
            state={state}
            mode="apply"
            onOpenTranslation={() => navigate('translation')}
            onOpenWorkbench={() => navigate('workbench')}
            onOpenGlossary={() => navigate('glossary')}
          />
        ));
      case 'pack-unpack':
        return toolPage('pack-unpack', <PackUnpackPage state={state} />);
      case 'ma-suite':
        return toolPage('ma-suite', <MaSuitePage state={state} />);
      case 'batch-correction':
        return toolPage('batch-correction', <BatchCorrectionPage state={state} />);
      case 'name-extraction':
        return toolPage('name-extraction', <NameExtractionPage state={state} />);
      case 'direct-rpy-translate':
        return toolPage('direct-rpy-translate', <DirectRpyTranslatePage state={state} onNavigate={navigate} />);
      case 'source-translate':
        return toolPage('source-translate', <SourceTranslatePage state={state} onNavigate={navigate} />);
      case 'hook-translate':
        return toolPage('hook-translate', <HookTranslatePage state={state} />);
      case 'hook-supplement':
        return toolPage('hook-supplement', <HookSupplementPage state={state} />);
      case 'font-replace':
        return toolPage('font-replace', <FontReplacePage state={state} />);
      case 'rpy-extraction':
        return toolPage('rpy-extraction', (
          <RpyExtractionPage
            state={state}
            onDirtyChange={setDirty}
            leaveGuardRef={rpyLeaveGuardRef}
            leaveBlockedRef={rpyLeaveBlockedRef}
          />
        ));
      case 'extract-to-tl':
        return toolPage('extract-to-tl', <ExtractToTlPage state={state} />);
      case 'extract-json':
        return toolPage('extract-json', <ExtractJsonPage state={state} />);
      case 'add-language':
        return toolPage('add-language', <AddLanguagePage state={state} />);
      case 'set-default-language':
        return toolPage('set-default-language', <SetDefaultLanguagePage state={state} />);
      case 'error-repair':
        return toolPage('error-repair', <ErrorRepairPage state={state} />);
      case 'translation-reuse':
        return toolPage('translation-reuse', <TranslationReusePage state={state} />);
      case 'android-build':
        return toolPage('android-build', <AndroidBuildPage state={state} />);
      case 'html-import':
        return toolPage('html-import', <HtmlImportPage state={state} />);
      case 'game-mod':
        return toolPage('game-mod', <GameModPage state={state} />);
      case 'project':
        return <ProjectPage state={state} />;
      case 'toolbox':
        return <ToolBoxPage state={state} onNavigate={navigate} />;
      case 'basic-settings':
        return <SettingsPage state={state} variant="basic" title={t('app_basic_settings_page')} description={t('basic_settings_page_header_description')} />;
      case 'expert-settings':
        return <SettingsPage state={state} variant="expert" title={t('app_expert_settings_page')} description={t('expert_settings_page_header_description')} />;
      case 'custom-prompt':
        return <CustomPromptPage state={state} onDirtyChange={setDirty} />;
      case 'app-settings':
        return <SettingsPage state={state} variant="app" title={t('app_settings_page')} description={t('app_settings_page_header_description')} />;
      case 'workbench':
        return <WorkbenchPage state={state} onDirtyChange={setDirty} onNavigate={navigate} />;
      case 'agent':
        return <AgentPage state={state} onOpenPlatforms={() => navigate('platform')} />;
      case 'platform':
        return <PlatformPage state={state} onDirtyChange={setDirty} />;
      default:
        return null;
    }
  })();

  return (
    <I18nContext.Provider value={t}>
    <div className="shell rb-shell">
      <header className="rb-titlebar">
        <span className="rb-brand">RenpyBox</span>
        {version ? <span className="rb-version">{version}</span> : null}
        <button
          type="button"
          className="workspace-project rb-project"
          title={projectPath || t('app_project_unbound_hint')}
          aria-label={`项目设置：${projectName}`}
          disabled={!state.ready}
          onClick={() => navigate('project')}
        >
          <Folder size={16} strokeWidth={1.75} />
          <span>{projectName}</span>
          <ChevronDown size={16} strokeWidth={1.75} />
        </button>
        <span className="rb-titlebar-spacer" />
        <span className="workspace-link rb-link" role="status" aria-label={linkText[link]}>
          <span className="rb-dot" data-state={link} />
          {link !== 'open' ? <span>{linkText[link]}</span> : null}
        </span>
        <div className="rb-window-controls">
          <button type="button" className="rb-titlebar-button" aria-label="最小化" onClick={() => window.renpy?.minimize?.()}>
            <IconChromeMinimize size={10} />
          </button>
          <button type="button" className="rb-titlebar-button" aria-label={maximized ? '向下还原' : '最大化'} onClick={() => window.renpy?.toggleMaximize?.()}>
            {maximized ? <IconChromeRestore size={10} /> : <IconChromeMaximize size={10} />}
          </button>
          <button type="button" className="rb-titlebar-button rb-titlebar-button-close" aria-label="关闭" onClick={() => navigate('close')}>
            <IconChromeClose size={10} />
          </button>
        </div>
      </header>

      <nav className="sidebar rb-sidebar" aria-label="主导航">
        <div className="sidebar-navigation rb-nav">
          {sections.map((section) => (
            <div key={section[0].key} className="rb-nav-section">
              {section.map((item) => {
                const Icon = NAV_ICONS[item.icon];
                const label = t(item.labelKey);
                return (
                  <Tooltip key={item.key} title={collapsed ? label : ''} placement="right">
                    <button
                      type="button"
                      className="nav-item rb-nav-item"
                      title={label}
                      aria-current={isNavCurrent(item, active) ? 'page' : undefined}
                      onClick={() => navigate(item.key)}
                    >
                      <Icon size={18} strokeWidth={1.75} />
                      <span className="rb-nav-label">{label}</span>
                    </button>
                  </Tooltip>
                );
              })}
            </div>
          ))}
        </div>

        <div className="sidebar-footer rb-sidebar-footer">
          <Tooltip title={collapsed ? t('app_toggle_theme') : ''} placement="right">
            <button type="button" className="nav-item rb-icon-button" title={t('app_toggle_theme')} aria-label={t('app_toggle_theme')} onClick={() => state.setTheme(state.theme === 'DARK' ? 'LIGHT' : 'DARK')}>
              {state.theme === 'DARK' ? <Sun size={18} strokeWidth={1.75} /> : <Moon size={18} strokeWidth={1.75} />}
            </button>
          </Tooltip>
          <Tooltip title={collapsed ? t('app_settings_page') : ''} placement="right">
            <button
              type="button"
              className="nav-item rb-icon-button"
              title={t('app_settings_page')}
              aria-label={t('app_settings_page')}
              aria-current={active === APP_SETTINGS_NAV.key ? 'page' : undefined}
              onClick={() => navigate(APP_SETTINGS_NAV.key)}
            >
              {(() => {
                const Icon = NAV_ICONS[APP_SETTINGS_NAV.icon];
                return <Icon size={18} strokeWidth={1.75} />;
              })()}
            </button>
          </Tooltip>
          {window.renpy ? <Tooltip title={collapsed ? t('app_logs') : ''} placement="right">
            <button
              type="button"
              className="nav-item rb-icon-button"
              title={t('app_logs')}
              aria-label={t('app_logs')}
              onClick={() => {
                void window.renpy?.openLogs().catch(error => {
                  state.pushToast('error', error instanceof Error ? error.message : String(error));
                });
              }}
            >
              <FileText size={18} strokeWidth={1.75} />
            </button>
          </Tooltip> : null}
        </div>
      </nav>

      <main className="content rb-content" data-page={active}>
        {link === 'closed' ? <div className="backend-notice rb-notice" role="status">
          {showDesktopRecovery ? (<>
            后端连接已断开，正在自动重试。若持续无法连接，请重启 RenpyBox，并点击左下角「日志」查看错误记录。
          </>) : (<>
            后端未连接，正在自动重试。请用 <code>npm run dev</code> 或 <code>npm run dev:web</code> 启动（二者共用同一后端，关桌面端不会杀掉服务）；仅 <code>npm run dev:renderer</code> 不会起 Python。
          </>)}
        </div> : null}
        <ErrorBoundary key={`${active}-${pageRetry}`} onRetry={() => setPageRetry((count) => count + 1)}>
          {state.ready ? body : <Empty>正在启动 …</Empty>}
        </ErrorBoundary>
      </main>

      {exitConfirm ? (
        <Dialog
          title={t('exit_title')}
          confirmText={t('exit_confirm')}
          cancelText={t('exit_cancel')}
          onCancel={() => { if (!closeInFlight.current) setExitConfirm(false); }}
          onConfirm={() => {
            if (closeInFlight.current) return;
            closeInFlight.current = true;
            void (async () => {
              try {
                if (!(await leaveRpyIfNeeded())) return;
                allowClose.current = true;
                window.renpy?.closeConfirmed?.();
              } finally {
                closeInFlight.current = false;
                setExitConfirm(false);
              }
            })();
          }}
        >{t('exit_description')}</Dialog>
      ) : null}
      {pendingPage ? (
        <Dialog
          title="放弃未保存修改？"
          confirmText={pendingPage === 'toolbox' ? '放弃修改并返回工具箱' : '放弃并继续'}
          cancelText="留在当前页"
          onCancel={() => setPendingPage(null)}
          onConfirm={() => {
          const next = pendingPage;
          void (async () => {
            // RPY：确认离开时先取消并等待真 worker 结束；失败则留在页并保持 dirty
            if (!(await leaveRpyIfNeeded())) {
              setPendingPage(null);
              return;
            }
            setPendingPage(null);
            setDirty(false);
            if (next === 'close') {
              allowClose.current = true;
              // 已在本 Dialog 确认放弃修改，主进程不再追加退出确认。
              window.renpy?.closeConfirmed?.();
            } else if (next) {
              setActive(next);
            }
          })();
        }}
        >离开当前页面会丢弃编辑内容，请先保存或导出。</Dialog>
      ) : null}
      <Toasts toasts={state.toasts} onDismiss={state.dismissToast} />
      {/* 桌面端：检查到新版本 / 刚完成更新时主动弹窗，不再只写进设置页。 */}
      <UpdateNotice />
    </div>
    </I18nContext.Provider>
  );
}

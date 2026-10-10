/**
 * 应用外壳：负责无边框窗口标题栏、主导航和页面切换。
 *
 * 业务页面继续复用现有 sidecar 状态与 API；壳层只维护布局，视觉令牌、
 * 交互状态和响应式细节集中在 styles.css。
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Notification, Tooltip } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { ChevronDown, FileText, Folder, Moon, Sun } from 'lucide-react';

import {
  IconChromeClose,
  IconChromeMaximize,
  IconChromeMinimize,
  IconChromeRestore,
  NAV_ICONS,
} from './icons';
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
import { createT, I18nContext } from './i18n';
import { Dialog, Empty } from './ui';
import { applyTheme } from './theme';
import type { AppState } from './useAppState';
import type { DesktopAppInfo } from './preload';

const TOAST_COLOR = { info: 'brand', success: 'green', warning: 'yellow', error: 'red' } as const;

type ToolPageKey = 'proofreading' | 'glossary' | 'preserve' | 'honorific';
const TOOL_PAGE_TOOL_KEY: Record<ToolPageKey, string> = {
  proofreading: 'proofreading',
  glossary: 'local_glossary',
  preserve: 'text_preserve',
  honorific: 'honorific_placeholder',
};
const TOOL_PAGE_DESC: Record<ToolPageKey, TextKey> = {
  proofreading: 'app_tool_desc_proofreading',
  glossary: 'app_tool_desc_glossary',
  preserve: 'app_tool_desc_preserve',
  honorific: 'app_tool_desc_honorific',
};

function Toasts(props: { toasts: AppState['toasts']; onDismiss: (id: number) => void }) {
  const { toasts, onDismiss } = props;
  if (toasts.length === 0) return null;
  return (
    <div className="rb-toasts">
      {toasts.map((toast) => (
        <Notification
          key={toast.id}
          data-rb-toast=""
          withBorder
          color={TOAST_COLOR[toast.tone]}
          onClose={() => onDismiss(toast.id)}
          closeButtonProps={{ 'aria-label': '知道了' }}
        >
          {toast.text}
        </Notification>
      ))}
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
  const [pendingPage, setPendingPage] = useState<PageKey | 'close' | null>(null);
  const navigate = (page: PageKey | 'close') => {
    if (page === active) return;
    if (dirty) { setPendingPage(page); return; }
    if (page === 'close') window.renpy?.close?.();
    else setActive(page);
  };

  // 系统关闭按钮或 Alt+F4 也要保护未保存编辑。
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty || allowClose.current) return;
      event.preventDefault(); event.returnValue = '';
      setPendingPage('close');
    };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  // 主题跟着配置走：用户在应用设置里改、点侧边栏切换都落到同一个字段。
  useEffect(() => {
    applyTheme(state.theme);
  }, [state.theme]);

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
  const collapsed = useMediaQuery('(max-width: 999px)') ?? false;
  const version = window.renpy ? desktopInfo?.appVersion ?? '' : state.version?.app_version ?? '';
  const showDesktopRecovery = Boolean(window.renpy) && desktopInfo?.packaged !== false;
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const projectName = projectPath.split(/[\\/]/).filter(Boolean).at(-1) || t('app_project_unbound_name');

  // 翻译页 preflight 判定缺资产时，让用户能直接跳到工作台补齐，
  // 不必自己找侧边栏（对齐 TranslationPage._open_workbench）。
  const [workbenchRequested, setWorkbenchRequested] = useState(0);
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
        return toolPage('glossary', <GlossaryPage state={state} onDirtyChange={setDirty} embedded />);
      case 'preserve':
        return toolPage('preserve', <PreservePage state={state} onDirtyChange={setDirty} />);
      case 'honorific':
        return toolPage('honorific', <HonorificPage state={state} onDirtyChange={setDirty} />);
      case 'project':
        return <ProjectPage state={state} />;
      case 'toolbox':
        return <ToolBoxPage state={state} onNavigate={navigate} />;
      case 'basic-settings':
        return <SettingsPage state={state} variant="basic" title={t('app_basic_settings_page')} description="调整翻译任务的并发、超时和重试阈值" />;
      case 'expert-settings':
        return <SettingsPage state={state} variant="expert" title={t('app_expert_settings_page')} description="控制提示词、资产分析和结果检查等高级行为" />;
      case 'custom-prompt':
        return <CustomPromptPage state={state} />;
      case 'app-settings':
        return <SettingsPage state={state} variant="app" title="应用设置" description="管理语言、更新、声音和应用级显示选项" />;
      case 'workbench':
        return <WorkbenchPage state={state} onDirtyChange={setDirty} />;
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
                  <Tooltip key={item.key} label={label} disabled={!collapsed} position="right">
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
          <Tooltip label={t('app_toggle_theme')} disabled={!collapsed} position="right">
            <button type="button" className="nav-item rb-icon-button" title={t('app_toggle_theme')} aria-label={t('app_toggle_theme')} onClick={() => state.setTheme(state.theme === 'DARK' ? 'LIGHT' : 'DARK')}>
              {state.theme === 'DARK' ? <Sun size={18} strokeWidth={1.75} /> : <Moon size={18} strokeWidth={1.75} />}
            </button>
          </Tooltip>
          <Tooltip label={t('app_settings_page')} disabled={!collapsed} position="right">
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
          {window.renpy ? <Tooltip label={t('app_logs')} disabled={!collapsed} position="right">
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
        {state.ready ? body : <Empty>正在启动 …</Empty>}
      </main>

      {pendingPage ? (
        <Dialog title="有未保存的修改" confirmText="放弃并继续" onCancel={() => setPendingPage(null)} onConfirm={() => {
          setDirty(false);
          if (pendingPage === 'close') { allowClose.current = true; window.renpy?.close?.(); }
          else setActive(pendingPage);
          setPendingPage(null);
        }}>离开当前页面会丢弃编辑内容，请先保存或导出。</Dialog>
      ) : null}
      <Toasts toasts={state.toasts} onDismiss={state.dismissToast} />
    </div>
    </I18nContext.Provider>
  );
}

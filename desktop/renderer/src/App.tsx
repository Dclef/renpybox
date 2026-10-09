/**
 * 应用外壳：负责无边框窗口标题栏、主导航和页面切换。
 *
 * 业务页面继续复用现有 sidecar 状态与 API；壳层只维护布局，视觉令牌、
 * 交互状态和响应式细节集中在 styles.css。
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { ConfigProvider, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';

import {
  IconChromeClose,
  IconChromeMaximize,
  IconChromeMinimize,
  IconChromeRestore,
  IconChevronRight,
  IconContrast,
  IconFolder,
  IconInfo,
  NAV_ICONS,
} from './icons';
import { APP_SETTINGS_NAV, findNavItem, navEntries, type PageKey } from './nav';
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
import { Dialog } from './ui';
import { applyTheme } from './theme';
import type { AppState } from './useAppState';

const LINK_TEXT: Record<'connecting' | 'open' | 'closed', string> = {
  connecting: '正在连接后端',
  open: '后端已连接',
  closed: '后端连接已断开',
};

function Toasts(props: { toasts: AppState['toasts']; onDismiss: (id: number) => void }) {
  const { toasts, onDismiss } = props;
  if (toasts.length === 0) return null;
  return (
    <div
      style={{
        position: 'fixed',
        right: 16,
        bottom: 76,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        width: 'min(360px, calc(100vw - 32px))',
        zIndex: 40,
      }}
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="banner" data-tone={toast.tone} role="status">
          <div style={{ flex: 1, minWidth: 0 }}>{toast.text}</div>
          <button type="button" className="btn" onClick={() => onDismiss(toast.id)}>
            知道了
          </button>
        </div>
      ))}
    </div>
  );
}

export function App(props: { state: AppState; link: 'connecting' | 'open' | 'closed' }) {
  const { state, link } = props;
  const [active, setActive] = useState<PageKey>('translation');
  const [maximized, setMaximized] = useState(false);
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

  const expertMode = state.settings?.values.expert_mode === true;
  const entries = useMemo(() => navEntries(expertMode), [expertMode]);
  const version = state.version?.app_version ?? '';
  const SettingsIcon = NAV_ICONS[APP_SETTINGS_NAV.icon];
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const projectName = projectPath.split(/[\\/]/).filter(Boolean).at(-1) || '未绑定项目';

  // 翻译页 preflight 判定缺资产时，让用户能直接跳到工作台补齐，
  // 不必自己找侧边栏（对齐 TranslationPage._open_workbench）。
  const [workbenchRequested, setWorkbenchRequested] = useState(0);
  useEffect(() => {
    if (workbenchRequested > 0) {
      setActive('workbench');
      setWorkbenchRequested(0);
    }
  }, [workbenchRequested]);

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
        return <ProofreadingPage state={state} onDirtyChange={setDirty} />;
      case 'glossary':
        return <GlossaryPage state={state} onDirtyChange={setDirty} />;
      case 'preserve':
        return <PreservePage state={state} onDirtyChange={setDirty} />;
      case 'honorific':
        return <HonorificPage state={state} onDirtyChange={setDirty} />;
      case 'project':
        return <ProjectPage state={state} />;
      case 'toolbox':
        return <ToolBoxPage state={state} onNavigate={navigate} />;
      case 'basic-settings':
        return (
          <SettingsPage
            state={state}
            variant="basic"
            title="基础设置"
            description="调整翻译任务的并发、超时和重试阈值"
          />
        );
      case 'expert-settings':
        return (
          <SettingsPage
            state={state}
            variant="expert"
            title="专家设置"
            description="控制提示词、资产分析和结果检查等高级行为"
          />
        );
      case 'app-settings':
        return <SettingsPage state={state} variant="app" title="应用设置" description="管理语言、更新、声音和应用级显示选项" />;
      case 'workbench':
        return <WorkbenchPage state={state} onDirtyChange={setDirty} />;
      case 'agent':
        return <AgentPage state={state} onOpenPlatforms={() => navigate('platform')} />;
      case 'platform':
        return <PlatformPage state={state} onDirtyChange={setDirty} />;
      case 'custom-prompt':
        return <CustomPromptPage state={state} />;
      default:
        return null;
    }
  })();

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: state.theme === 'DARK' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#0078D4',
          borderRadius: 4,
          fontFamily: "'Segoe UI Variable', 'Segoe UI', 'Microsoft YaHei UI', system-ui, sans-serif",
        },
      }}
    >
    <div className="shell">
      <header className="titlebar">
        <span className="titlebar-title">RenpyBox {version}</span>
        <span className="titlebar-spacer" />
        <div className="titlebar-controls">
          <button
            type="button"
            className="titlebar-button"
            aria-label="最小化"
            onClick={() => window.renpy?.minimize?.()}
          >
            <IconChromeMinimize size={10} />
          </button>
          <button
            type="button"
            className="titlebar-button"
            aria-label={maximized ? '向下还原' : '最大化'}
            onClick={() => window.renpy?.toggleMaximize?.()}
          >
            {maximized ? <IconChromeRestore size={10} /> : <IconChromeMaximize size={10} />}
          </button>
          <button
            type="button"
            className="titlebar-button titlebar-button-close"
            aria-label="关闭"
            onClick={() => navigate('close')}
          >
            <IconChromeClose size={10} />
          </button>
        </div>
      </header>

      <nav className="sidebar" aria-label="主导航">
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">R</span>
          <span className="brand-copy">
            <strong>RenpyBox</strong>
            <small>Ren'Py 本地化工作台</small>
          </span>
        </div>
        <div className="sidebar-navigation">
          {entries.map((entry) =>
            entry.kind === 'group' ? (
              <h2 key={entry.id} className="nav-group-label">{entry.label}</h2>
            ) : (
              <button
                key={entry.item.key}
                type="button"
                className="nav-item"
                title={entry.item.label}
                aria-current={active === entry.item.key ? 'page' : undefined}
                onClick={() => navigate(entry.item.key)}
              >
                <span className="nav-item-icon">
                  {(() => {
                    const Icon = NAV_ICONS[entry.item.icon];
                    return <Icon size={18} />;
                  })()}
                </span>
                <span className="nav-item-label">{entry.item.label}</span>
              </button>
            ),
          )}
        </div>

        <div className="sidebar-footer">
          <button
            type="button"
            className="nav-item"
            title={APP_SETTINGS_NAV.label}
            aria-current={active === APP_SETTINGS_NAV.key ? 'page' : undefined}
            onClick={() => navigate(APP_SETTINGS_NAV.key)}
          >
            <span className="nav-item-icon">
              <SettingsIcon size={18} />
            </span>
            <span className="nav-item-label">{APP_SETTINGS_NAV.label}</span>
          </button>

          <button
            type="button"
            className="nav-item"
            title="切换主题"
            onClick={() => state.setTheme(state.theme === 'DARK' ? 'LIGHT' : 'DARK')}
          >
            <span className="nav-item-icon">
              <IconContrast size={18} />
            </span>
            <span className="nav-item-label">切换主题</span>
          </button>

          {state.health ? (
            <button
              type="button"
              className="nav-item"
              title="关于与诊断"
              onClick={() => {
                // 壳窗口是 vanilla 页面，不进主 UI bundle；这里按需唤起。
                void window.renpy?.openShell('welcome');
              }}
            >
              <span className="nav-item-icon">
                <IconInfo size={18} />
              </span>
              <span className="nav-item-label">关于与诊断</span>
            </button>
          ) : null}
        </div>
      </nav>

      <main className="content" data-page={active}>
        <div className="workspace-bar">
          <div className="workspace-breadcrumb">
            <button type="button" className="workspace-project" title={projectPath || '尚未绑定 Ren\'Py 项目，点击前往项目设置'} aria-label={`项目设置：${projectName}`} disabled={!state.ready} onClick={() => navigate('project')}>
              <IconFolder size={15} />
              <span>{projectName}</span>
            </button>
            <IconChevronRight size={12} />
            <span className="workspace-current">{findNavItem(active).label}</span>
          </div>
          <span className="workspace-link" role="status" aria-label={LINK_TEXT[link]}>
            <span className="sidebar-status-dot" data-state={link} />
            <span className="workspace-link-text">{LINK_TEXT[link]}</span>
          </span>
        </div>
        {link === 'closed' ? <div className="backend-notice" role="status">
          后端未连接，正在自动重试。请用 <code>npm run dev</code> 或 <code>npm run dev:web</code> 启动（二者共用同一后端，关桌面端不会杀掉服务）；仅 <code>npm run dev:renderer</code> 不会起 Python。
        </div> : null}
        {state.ready ? (
          body
        ) : (
          <div className="page">
            <div className="empty">正在启动 …</div>
          </div>
        )}
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
    </ConfigProvider>
  );
}

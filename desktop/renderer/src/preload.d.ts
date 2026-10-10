/** preload 暴露的窗口能力（见 main/preload-main.cjs）。 */

interface FileDialogFilter { name: string; extensions: string[] }
interface FileDialogOptions { defaultPath?: string; filters?: FileDialogFilter[] }

export interface DesktopUpdateState {
  status: 'dev' | 'idle' | 'checking' | 'available' | 'latest' | 'downloading' | 'downloaded' | 'error';
  currentVersion: string;
  version: string;
  error: string;
  progress: number;
  releaseNotes?: string;
  releaseUrl?: string;
  packaged: boolean;
}

export interface DesktopAppInfo {
  appVersion: string;
  packaged: boolean;
  logPath: string;
  dataPath: string;
  icon: string;
  health?: { ok?: boolean; port?: number; python_version?: string };
}

interface RenpyBridge {
  sidecar: () => Promise<unknown>;
  appInfo: () => Promise<DesktopAppInfo>;
  changelog: () => Promise<string>;
  /** 在应用内打开运行日志窗口。 */
  openLogs: () => Promise<void>;
  updater: {
    state: () => Promise<DesktopUpdateState>;
    check: () => Promise<DesktopUpdateState>;
    download: () => Promise<DesktopUpdateState>;
    cancel: () => Promise<DesktopUpdateState>;
    install: () => Promise<unknown>;
    onState: (callback: (state: DesktopUpdateState) => void) => () => void;
  };
  /** 打开日志或更新窗口；welcome 是旧日志入口的兼容别名。 */
  openShell: (kind: 'logs' | 'welcome' | 'update') => Promise<void>;
  /** 关闭当前窗口；主窗口会先弹出退出确认 */
  close: () => void;
  /** 未保存修改已在页面内确认放弃时关闭主窗口，不再弹退出确认 */
  closeConfirmed: () => void;
  /** 无边框窗口的窗口控制（标题栏右侧三个按钮） */
  minimize: () => void;
  toggleMaximize: () => void;
  /** 订阅最大化状态变化，返回取消订阅函数 */
  onMaximizeChange: (callback: (maximized: boolean) => void) => () => void;
  /** 目录选择（原生 dialog）与「打开目录」；取消返回 null */
  pickFolder: (defaultPath?: string) => Promise<string | null>;
  pickFile: (options?: FileDialogOptions) => Promise<string | null>;
  saveFile: (options?: FileDialogOptions) => Promise<string | null>;
  openPath: (target: string) => Promise<boolean>;
  platform: string;
  versions: { electron: string; chrome: string; node: string };
}

declare global {
  interface Window {
    renpy?: RenpyBridge;
  }
}

export {};

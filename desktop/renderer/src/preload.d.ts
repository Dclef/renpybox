/** preload 暴露的窗口能力（见 main/preload-main.cjs）。 */

interface RenpyBridge {
  sidecar: () => Promise<unknown>;
  /** 打开轻量壳窗口：'welcome'（关于与诊断）/ 'update'（更新） */
  openShell: (kind: 'welcome' | 'update') => Promise<void>;
  close: () => void;
  /** 无边框窗口的窗口控制（标题栏右侧三个按钮） */
  minimize: () => void;
  toggleMaximize: () => void;
  /** 订阅最大化状态变化，返回取消订阅函数 */
  onMaximizeChange: (callback: (maximized: boolean) => void) => () => void;
  /** 目录选择（原生 dialog）与「打开目录」；取消返回 null */
  pickFolder: (defaultPath?: string) => Promise<string | null>;
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
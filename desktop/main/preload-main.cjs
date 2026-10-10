/**
 * 主窗口 preload。sandbox: true 环境下必须用 CommonJS。
 * 只暴露必要能力，不把 ipcRenderer 本身漏出去。
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('renpy', {
  sidecar: () => ipcRenderer.invoke('sidecar:info'),
  appInfo: () => ipcRenderer.invoke('app:info'),
  changelog: () => ipcRenderer.invoke('app:changelog'),
  openLogs: () => ipcRenderer.invoke('app:open-logs'),
  updater: {
    state: () => ipcRenderer.invoke('app:update-state'),
    check: () => ipcRenderer.invoke('app:check-update'),
    download: () => ipcRenderer.invoke('app:download-update'),
    cancel: () => ipcRenderer.invoke('app:cancel-update'),
    install: () => ipcRenderer.invoke('app:install-update'),
    onState: (callback) => {
      const handler = (_event, state) => callback(state);
      ipcRenderer.on('app:update-state', handler);
      return () => ipcRenderer.removeListener('app:update-state', handler);
    },
  },
  /** 打开日志 / 更新窗口。 */
  openShell: (kind) => ipcRenderer.invoke('shell:open', kind),
  close: () => ipcRenderer.send('shell:close'),
  /** 无边框窗口的窗口控制（渲染端画在 38px 标题栏右侧） */
  minimize: () => ipcRenderer.send('window:minimize'),
  toggleMaximize: () => ipcRenderer.send('window:toggle-maximize'),
  /** 订阅最大化状态变化，返回取消订阅函数 */
  onMaximizeChange: (callback) => {
    const handler = (_event, maximized) => callback(maximized);
    ipcRenderer.on('window:maximized', handler);
    return () => ipcRenderer.removeListener('window:maximized', handler);
  },
  /*
   * 目录选择与「打开目录」：渲染端没有 fs / dialog，必须走主进程。
   * 原壳用 QFileDialog.getExistingDirectory + webbrowser.open，这里是等价物。
   */
  pickFolder: (defaultPath) => ipcRenderer.invoke('dialog:pick-folder', defaultPath),
  pickFile: (options) => ipcRenderer.invoke('dialog:pick-file', options),
  saveFile: (options) => ipcRenderer.invoke('dialog:save-file', options),
  openPath: (target) => ipcRenderer.invoke('shell:open-path', target),
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
});

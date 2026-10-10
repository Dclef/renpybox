/**
 * 壳窗口 preload（日志 / 更新弹窗）。
 * 故意保持极小：壳页面是 vanilla 的，不该也不需要访问 sidecar。
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('shellBridge', {
  isShellWindow: true,
  appInfo: () => ipcRenderer.invoke('app:info'),
  openLogs: () => ipcRenderer.invoke('app:open-logs'),
  logs: {
    read: (source = 'app') => ipcRenderer.invoke('app:read-logs', source),
    copy: text => ipcRenderer.invoke('app:copy-logs', text),
  },
  openExternal: url => ipcRenderer.invoke('app:open-external', url),
  updater: {
    state: () => ipcRenderer.invoke('app:update-state'),
    check: () => ipcRenderer.invoke('app:check-update'),
    download: () => ipcRenderer.invoke('app:download-update'),
    cancel: () => ipcRenderer.invoke('app:cancel-update'),
    install: () => ipcRenderer.invoke('app:install-update'),
    onState: callback => {
      const handler = (_event, state) => callback(state);
      ipcRenderer.on('app:update-state', handler);
      return () => ipcRenderer.removeListener('app:update-state', handler);
    },
  },
  close: () => ipcRenderer.send('shell:close'),
  versions: { electron: process.versions.electron, chrome: process.versions.chrome },
});

/**
 * 壳窗口 preload（欢迎页 / 更新弹窗）。
 * 故意保持极小：壳页面是 vanilla 的，不该也不需要访问 sidecar。
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('shellBridge', {
  isShellWindow: true,
  close: () => ipcRenderer.send('shell:close'),
  versions: { electron: process.versions.electron, chrome: process.versions.chrome },
});
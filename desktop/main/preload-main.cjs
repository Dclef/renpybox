/**
 * 主窗口 preload。sandbox: true 环境下必须用 CommonJS。
 * 只暴露必要能力，不把 ipcRenderer 本身漏出去。
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('renpy', {
  sidecar: () => ipcRenderer.invoke('sidecar:info'),
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
});
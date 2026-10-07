/**
 * RenpyBox desktop shell —— Electron 主进程。
 *
 * 设计对齐 DeepSeek Harness（@deepseek-ai/dsh-desktop）的壳工程模式：
 *   1. sidecar 探活后才开窗，避免白屏
 *   2. 多 preload 按窗口职责拆分（主窗口 / 壳窗口各一个）
 *   3. sandbox + contextIsolation + 严格 CSP，渲染端拿不到任意能力
 *   4. 轻量壳页（欢迎 / 更新）用 vanilla，不进主 UI bundle
 *
 * 与 DeepSeek 的差异（有意为之）：
 *   - 主 UI 本地加载，不做远程 loadURL（RenpyBox 必须离线可用）
 *   - sidecar 是 Python 而非 Node（Ren'Py 生态依赖）
 */
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Sidecar, SIDECAR_PORT, SIDECAR_URL } from './sidecar.js';

// electron 是主进程内建模块，ESM 下用 createRequire 取最稳
const require = createRequire(import.meta.url);
const { app, BrowserWindow, Menu, ipcMain, shell, globalShortcut } = require('electron');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_ROOT = path.resolve(__dirname, '..');
const RENDERER_DIST = path.join(DESKTOP_ROOT, 'dist', 'index.html');
const SHELL_DIR = path.join(DESKTOP_ROOT, 'shell');

const isDev = !app.isPackaged;
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || 'http://127.0.0.1:5173';

const log = (...args) => console.log(...args);
const sidecar = new Sidecar({ onLog: log });

let mainWindow = null;

function webPreferences(preloadFile) {
  return {
    preload: path.join(__dirname, preloadFile),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
    spellcheck: false,
  };
}

async function createMainWindow() {
  const started = Date.now();
  const info = await sidecar.start();
  log(`[shell] sidecar 就绪 ${JSON.stringify(info)}，耗时 ${Date.now() - started}ms`);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 680,
    show: false,
    backgroundColor: '#17263d',
    title: 'RenpyBox',
    webPreferences: webPreferences('preload-main.cjs'),
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    await mainWindow.loadURL(DEV_SERVER_URL);
  } else {
    await mainWindow.loadFile(RENDERER_DIST);
  }
}

/** 轻量壳窗口：vanilla 页面 + 独立 preload，按 DeepSeek 的做法不背 UI 框架 */
function openShellWindow(kind) {
  const win = new BrowserWindow({
    width: kind === 'welcome' ? 760 : 520,
    height: kind === 'welcome' ? 580 : 400,
    resizable: false,
    show: false,
    frame: kind !== 'update',
    backgroundColor: '#17263d',
    webPreferences: webPreferences('preload-shell.cjs'),
  });
  win.once('ready-to-show', () => win.show());
  win.loadFile(path.join(SHELL_DIR, `${kind}.html`));
  return win;
}

ipcMain.handle('sidecar:info', () => ({
  port: SIDECAR_PORT,
  http: SIDECAR_URL,
  appVersion: app.getVersion(),
  electron: process.versions.electron,
  chrome: process.versions.chrome,
}));

// M0 spike 用快捷键触发壳窗口，方便验证多 preload 拆分是否生效
function registerShortcuts() {
  globalShortcut.register('CommandOrControl+Shift+W', () => openShellWindow('welcome'));
  globalShortcut.register('CommandOrControl+Shift+U', () => openShellWindow('update'));
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  try {
    await createMainWindow();
    registerShortcuts();
  } catch (err) {
    log('[shell] 启动失败：', err);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow().catch(() => {});
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', async (event) => {
  event.preventDefault();
  globalShortcut.unregisterAll();
  await sidecar.stop();
  app.exit(0);
});
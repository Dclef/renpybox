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
const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_ROOT = path.resolve(__dirname, '..');
const RENDERER_DIST = path.join(DESKTOP_ROOT, 'dist', 'index.html');
const SHELL_DIR = path.join(DESKTOP_ROOT, 'shell');

const isDev = !app.isPackaged;
// dev 端口必须与 vite.config.ts 的 WEB_PORT 一致（默认 5173）。
// 脚本会显式传 VITE_DEV_SERVER_URL；直接 `npm run dev` 时靠这个默认值。
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

  // 尺寸对齐 AppFluentWindow：默认 1280x800、APP_MIN_WIDTH/HEIGHT = 900/640。
  // frame: false —— 原壳是 qfluentwidgets 的无边框 FluentWindow，标题栏由窗口自己画，
  // 保留系统边框会出现两条标题栏。
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 640,
    frame: false,
    show: false,
    backgroundColor: '#202020',
    title: 'RenpyBox',
    webPreferences: webPreferences('preload-main.cjs'),
  });

  // 最大化状态回推给渲染端，标题栏右侧的「最大化 / 还原」图标才能对上。
  const forwardMaximizeState = () => {
    mainWindow.webContents.send('window:maximized', mainWindow.isMaximized());
  };
  mainWindow.on('maximize', forwardMaximizeState);
  mainWindow.on('unmaximize', forwardMaximizeState);

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

ipcMain.handle('shell:open', (_event, kind) => {
  if (kind === 'welcome' || kind === 'update') openShellWindow(kind);
});

ipcMain.on('shell:close', (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close();
});

// 无边框窗口的控制按钮由渲染端画在 38px 标题栏右侧，这里只做转发。
ipcMain.on('window:minimize', (event) => {
  BrowserWindow.fromWebContents(event.sender)?.minimize();
});

ipcMain.on('window:toggle-maximize', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return;
  if (win.isMaximized()) win.unmaximize();
  else win.maximize();
});

// 目录选择 / 打开目录。原壳用 QFileDialog.getExistingDirectory + webbrowser.open，
// 渲染端没有 fs 与 dialog，这两件事只能由主进程提供。
ipcMain.handle('dialog:pick-folder', async (event, defaultPath) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const result = await dialog.showOpenDialog(win, {
    properties: ['openDirectory'],
    defaultPath: typeof defaultPath === 'string' && defaultPath ? defaultPath : undefined,
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

ipcMain.handle('shell:open-path', async (_event, target) => {
  if (typeof target !== 'string' || !target) return false;
  return (await shell.openPath(target)) === '';
});

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  try {
    await createMainWindow();
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
  // 仅杀死本进程启动的 sidecar；EXTERNAL / 复用模式下保留后端给网页端。
  await sidecar.stop();
  app.exit(0);
});
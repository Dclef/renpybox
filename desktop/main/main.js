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
import { fileURLToPath, pathToFileURL } from 'node:url';
import { mkdirSync, readFileSync } from 'node:fs';
import { Sidecar, SIDECAR_PORT, SIDECAR_URL } from './sidecar.js';
import { createLogger } from './logger.js';
import { readLogTail } from './log-reader.js';
import { createDesktopUpdater } from './updater.js';

// electron 是主进程内建模块，ESM 下用 createRequire 取最稳
const require = createRequire(import.meta.url);
const { app, BrowserWindow, Menu, dialog, ipcMain, shell, clipboard, nativeTheme } = require('electron');
const { autoUpdater } = require('electron-updater');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DESKTOP_ROOT = path.resolve(__dirname, '..');
const RENDERER_DIST = path.join(DESKTOP_ROOT, 'dist', 'index.html');
const SHELL_DIR = path.join(DESKTOP_ROOT, 'shell');

const isDev = !app.isPackaged;
if (!isDev) {
  const profile = app.commandLine.getSwitchValue('user-data-dir');
  app.setPath('userData', profile ? path.resolve(profile) : path.join(app.getPath('appData'), 'RenpyBox-newUI'));
}
if (!app.requestSingleInstanceLock()) app.exit(0);
// dev 端口必须与 vite.config.ts 的 WEB_PORT 一致（默认 5173）。
// 脚本会显式传 VITE_DEV_SERVER_URL；直接 `npm run dev` 时靠这个默认值。
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL || 'http://127.0.0.1:5173';

const dataPath = isDev ? path.resolve(DESKTOP_ROOT, '..') : app.getPath('userData');
const logDirectory = path.join(dataPath, 'log');
const appIcon = isDev ? path.join(DESKTOP_ROOT, '..', 'resource', 'icon.ico') : path.join(process.resourcesPath, 'renpybox', 'icon.ico');
let log;
try {
  mkdirSync(dataPath, { recursive: true });
  log = createLogger(logDirectory);
  log(`启动 RenpyBox ${app.getVersion()}`);
} catch (error) {
  dialog.showErrorBox('RenpyBox 启动失败', `无法写入运行目录：${dataPath}\n\n${error.message || error}`);
  app.exit(1);
  throw error;
}
const sidecar = new Sidecar({
  onLog: line => line.startsWith('[backend') ? log.debug(line) : log(line),
  backendExecutable: isDev ? undefined : path.join(process.resourcesPath, 'backend', 'RenpyBoxBackend.exe'),
  appRoot: dataPath,
  expectedAppVersion: app.getVersion().split('-')[0],
  allowReuse: isDev,
});

let mainWindow = null;
let logWindow = null;
let backendHealth = null;
let quitting = false;
let cleanupDone = false;
const updater = createDesktopUpdater({
  autoUpdater, packaged: !isDev, version: app.getVersion(), log,
  broadcast: state => {
    for (const win of BrowserWindow.getAllWindows()) {
      if (!win.isDestroyed()) win.webContents.send('app:update-state', state);
    }
  },
  beforeInstall: async () => { await sidecar.stop(); cleanupDone = true; },
});
app.on('second-instance', () => {
  if (mainWindow && !mainWindow.isDestroyed()) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); }
});

function openExternal(url) {
  try { const parsed = new URL(url); if (['https:', 'http:'].includes(parsed.protocol)) return shell.openExternal(parsed.href); } catch {}
  return Promise.reject(new Error('仅支持打开 HTTP/HTTPS 链接。'));
}

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
  backendHealth = info;
  log(`后端就绪，耗时 ${Date.now() - started}ms`);

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
    icon: appIcon,
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
    void openExternal(url).catch(error => log.error(error));
    return { action: 'deny' };
  });

  if (isDev) {
    await mainWindow.loadURL(DEV_SERVER_URL);
  } else {
    await mainWindow.loadFile(RENDERER_DIST);
  }
  mainWindow.on('closed', () => { mainWindow = null; });
}

/** 轻量壳窗口：vanilla 页面 + 独立 preload，按 DeepSeek 的做法不背 UI 框架 */
function openShellWindow(kind) {
  const isLogs = kind === 'logs' || kind === 'welcome';
  if (isLogs && logWindow && !logWindow.isDestroyed()) {
    if (logWindow.isMinimized()) logWindow.restore();
    logWindow.show();
    logWindow.focus();
    return logWindow;
  }
  const win = new BrowserWindow({
    width: isLogs ? 900 : 520,
    height: isLogs ? 600 : 400,
    ...(isLogs ? { minWidth: 560, minHeight: 360, parent: mainWindow || undefined, title: '运行日志 — RenpyBox' } : {}),
    resizable: isLogs,
    show: false,
    frame: kind !== 'update',
    backgroundColor: isLogs ? (nativeTheme.shouldUseDarkColors ? '#181818' : '#ffffff') : '#17263d',
    icon: appIcon,
    webPreferences: webPreferences('preload-shell.cjs'),
  });
  if (isLogs) { logWindow = win; win.on('closed', () => { logWindow = null; }); }
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => { void openExternal(url).catch(error => log.error(error)); return { action: 'deny' }; });
  void win.loadFile(path.join(SHELL_DIR, kind === 'update' ? 'update-dialog.html' : 'welcome.html')).catch(error => log.error(error));
  return win;
}
ipcMain.handle('sidecar:info', () => ({
  port: SIDECAR_PORT,
  http: SIDECAR_URL,
  appVersion: app.getVersion(),
  electron: process.versions.electron,
  chrome: process.versions.chrome,
}));
ipcMain.handle('app:info', async () => {
  try { backendHealth = await sidecar.probe(); } catch { backendHealth = { ok: false, port: SIDECAR_PORT }; }
  return { appVersion: app.getVersion(), packaged: !isDev, logPath: log.path, dataPath, icon: pathToFileURL(appIcon).href, health: { ...backendHealth, port: SIDECAR_PORT } };
});
ipcMain.handle('app:changelog', () => readFileSync(isDev ? path.join(DESKTOP_ROOT, '..', 'CHANGELOG.md') : path.join(process.resourcesPath, 'renpybox', 'CHANGELOG.md'), 'utf8'));
ipcMain.handle('app:open-logs', () => { openShellWindow('logs'); });
ipcMain.handle('app:read-logs', (_event, source = 'app') => {
  const filename = source === 'app' ? 'app.log' : source === 'desktop' ? 'desktop.log' : null;
  if (!filename) throw new Error('未知日志类型');
  return readLogTail(path.join(logDirectory, filename));
});
ipcMain.handle('app:copy-logs', (_event, text) => {
  if (typeof text !== 'string' || text.length > 512 * 1024) throw new Error('日志内容无效');
  clipboard.writeText(text);
});
ipcMain.handle('app:open-external', (_event, url) => openExternal(url));
ipcMain.handle('app:update-state', () => updater.state());
ipcMain.handle('app:check-update', () => updater.check());
ipcMain.handle('app:download-update', () => updater.download());
ipcMain.handle('app:cancel-update', () => updater.cancel());
ipcMain.handle('app:install-update', () => updater.install());

ipcMain.handle('shell:open', (_event, kind) => {
  if (kind === 'logs' || kind === 'welcome' || kind === 'update') openShellWindow(kind);
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

function sanitizeDialogOptions(options) {
  const source = options && typeof options === 'object' ? options : {};
  const defaultPath = typeof source.defaultPath === 'string' && source.defaultPath ? source.defaultPath : undefined;
  const filters = Array.isArray(source.filters)
    ? source.filters
        .filter((item) => item && typeof item.name === 'string' && Array.isArray(item.extensions))
        .map((item) => ({
          name: item.name,
          extensions: item.extensions.filter((ext) => typeof ext === 'string' && /^[a-z0-9]{1,10}$/i.test(ext)),
        }))
        .filter((item) => item.extensions.length > 0)
    : [];
  return { defaultPath, filters: filters.length ? filters : undefined };
}

ipcMain.handle('dialog:pick-file', async (event, options) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const result = await dialog.showOpenDialog(win, {
    properties: ['openFile'],
    ...sanitizeDialogOptions(options),
  });
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0];
});

ipcMain.handle('dialog:save-file', async (event, options) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  const result = await dialog.showSaveDialog(win, sanitizeDialogOptions(options));
  if (result.canceled || !result.filePath) return null;
  return result.filePath;
});

ipcMain.handle('shell:open-path', async (_event, target) => {
  if (typeof target !== 'string' || !target) return false;
  return (await shell.openPath(target)) === '';
});

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  if (!isDev) app.setAppUserModelId('com.dclef.renpybox.newui');
  try {
    await createMainWindow();
    if (!isDev) setTimeout(() => void updater.check(), 2500).unref();
  } catch (err) {
    log.error('启动失败', err);
    dialog.showErrorBox('RenpyBox 启动失败', `${err.message || err}\n\n日志：${log.path}`);
    await sidecar.stop();
    app.exit(1);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow().catch(error => { log.error(error); dialog.showErrorBox('RenpyBox', error.message); });
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', (event) => {
  if (cleanupDone) return;
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  void sidecar.stop().catch(error => log.error(error)).finally(() => { cleanupDone = true; app.quit(); });
});

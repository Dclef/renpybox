const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { once } = require('node:events');

app.disableHardwareAcceleration();
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'renpybox-recovery-check-')));
let win;
const timeout = setTimeout(() => { console.error('FAIL Window recovery timed out'); app.exit(1); }, 20000);
app.whenReady().then(async () => {
  const { createWindowCloseGuard } = await import(pathToFileURL(path.resolve(__dirname, '../main/window-close-guard.js')).href);
  win = new BrowserWindow({ show: false, webPreferences: {
    preload: path.resolve(__dirname, '../main/preload-main.cjs'),
    sandbox: true, contextIsolation: true, nodeIntegration: false,
  } });
  let quitting = false;
  let exits = 0;
  let dialogCount = 0;
  let resolveQuit;
  const quitRequested = new Promise(resolve => { resolveQuit = resolve; });
  const guard = createWindowCloseGuard({
    window: win,
    isQuitting: () => quitting,
    getLocale: () => 'EN',
    showMessageBox: async (_owner, options) => {
      assert.equal(options.defaultId, 2);
      assert.equal(options.cancelId, 2);
      dialogCount += 1;
      return { response: dialogCount === 1 ? 0 : 1 };
    },
    requestQuit: () => { exits += 1; quitting = true; guard.beginQuit(); resolveQuit(); },
  });
  await win.loadURL('data:text/html;charset=utf-8,<title>Recovery fixture</title><p>Isolated renderer</p>');
  // executeJavaScript must not return the bridge's unsubscribe function (not cloneable).
  await win.webContents.executeJavaScript(`window.__closeRequests = 0; window.renpy.onCloseRequested(() => { window.__closeRequests += 1; }); void 0;`);
  win.close();
  await win.webContents.executeJavaScript(`new Promise(resolve => { const check = () => window.__closeRequests ? resolve(window.__closeRequests) : setTimeout(check, 10); check(); })`);
  assert.equal(win.isDestroyed(), false);
  assert.equal(await win.webContents.executeJavaScript('window.__closeRequests'), 1);
  assert.equal(dialogCount, 0);
  console.log('PASS Healthy renderer handles close without a native dialog');

  const gone = once(win.webContents, 'render-process-gone');
  win.webContents.forcefullyCrashRenderer();
  await gone;
  const reloaded = once(win.webContents, 'did-finish-load');
  win.close();
  await reloaded;
  assert.equal(win.isDestroyed(), false);
  assert.equal(win.webContents.isCrashed(), false);
  assert.equal(dialogCount, 1);
  assert.equal(exits, 0);
  assert.equal(await win.webContents.executeJavaScript('document.title'), 'Recovery fixture');
  console.log('PASS Crashed renderer reloads and can execute JavaScript again');

  const goneAgain = once(win.webContents, 'render-process-gone');
  win.webContents.forcefullyCrashRenderer();
  await goneAgain;
  win.close();
  await quitRequested;
  assert.equal(win.isDestroyed(), false, 'Keep the window until backend cleanup is complete');
  const closed = once(win, 'closed');
  guard.finishQuit();
  await closed;
  assert.equal(dialogCount, 2);
  assert.equal(exits, 1);
  assert.equal(win.isDestroyed(), true);
  console.log('PASS Native quit waits for cleanup, then destroys the crashed window');
  clearTimeout(timeout);
  console.log('ALL WINDOW RECOVERY CHECKS PASSED');
  app.exit(0);
}).catch(error => {
  console.error(error);
  clearTimeout(timeout);
  if (win && !win.isDestroyed()) win.destroy();
  app.exit(1);
});

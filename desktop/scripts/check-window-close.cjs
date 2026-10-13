/* Isolated Electron checks: no application entry point, backend, or user processes. */
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { mkdtempSync, readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { app, BrowserWindow } = require('electron');

app.setPath('userData', mkdtempSync(path.join(os.tmpdir(), 'renpybox-close-check-')));
app.on('window-all-closed', () => {});
const owned = new Set();
const watchdog = setTimeout(() => { console.error('FAIL close check timed out'); app.exit(1); }, 45000);
const tick = () => new Promise(resolve => setImmediate(resolve));
function bounded(promise, label) {
  let timer;
  return Promise.race([promise, new Promise((_resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out`)), 8000);
  })]).finally(() => clearTimeout(timer));
}

app.whenReady().then(async () => {
  const { createWindowCloseGuard } = await import(pathToFileURL(path.join(__dirname, '..', 'main', 'window-close-guard.js')).href);
  let passed = 0;
  async function check(label, run) {
    await run();
    console.log(`PASS ${label}`);
    passed += 1;
  }
  async function fixture({ requestQuit } = {}) {
    const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
    owned.add(win); win.once('closed', () => owned.delete(win));
    const f = { win, contents: win.webContents, dialogs: [], requests: 0, quitting: false, quitCalls: 0, errors: [], events: [] };
    for (const name of ['did-start-loading', 'did-finish-load', 'render-process-gone']) f.contents.on(name, () => f.events.push(name));
    f.contents.on('did-fail-load', (_event, code, text) => f.events.push(`did-fail-load ${code} ${text}`));
    const originalSend = f.contents.send.bind(f.contents);
    f.contents.send = (channel, ...args) => {
      if (channel === 'window:close-requested') f.requests += 1;
      return originalSend(channel, ...args);
    };
    f.guard = createWindowCloseGuard({ window: win,
      showMessageBox: (_owner, options) => new Promise(resolve => f.dialogs.push({ options, resolve })),
      requestQuit: requestQuit || (() => { f.quitCalls += 1; f.quitting = true; f.guard.beginQuit(); }),
      isQuitting: () => f.quitting, getLocale: () => 'EN', log: error => f.errors.push(error),
    });
    await win.loadURL('data:text/html;charset=utf-8,<title>RenpyBox isolated close check</title><body>test</body>');
    f.hang = async () => {
      const started = bounded(new Promise(resolve => {
        const onMessage = event => {
          if (event.message !== 'RENPYBOX_CLOSE_CHECK_HANG') return;
          f.contents.removeListener('console-message', onMessage);
          resolve();
        };
        f.contents.on('console-message', onMessage);
      }), 'renderer entered infinite loop');
      // The pending call rejects when recovery kills its renderer; consume that rejection.
      void f.contents.executeJavaScript("console.log('RENPYBOX_CLOSE_CHECK_HANG'); for (;;) {}").catch(() => {});
      await started;
    };
    f.crash = async () => {
      const gone = bounded(once(f.contents, 'render-process-gone'), 'renderer crash');
      f.contents.forcefullyCrashRenderer(); await gone;
    };
    f.dispose = () => { f.guard.dispose(); if (!win.isDestroyed()) win.destroy(); };
    return f;
  }

  await check('healthy close uses renderer confirmation', async () => {
    const f = await fixture();
    f.win.close();
    assert.equal(f.requests, 1); assert.equal(f.dialogs.length, 0); assert.equal(f.win.isDestroyed(), false);
    const closed = bounded(once(f.win, 'closed'), 'confirmed close');
    f.guard.confirm(); await closed;
    assert.equal(f.errors.length, 0);
  });

  await check('healthy dirty beforeunload stays blocked; committed quit releases it', async () => {
    const f = await fixture();
    await f.contents.executeJavaScript('window.onbeforeunload = () => false; void 0');
    const blocked = bounded(once(f.contents, 'will-prevent-unload'), 'dirty veto');
    f.guard.confirm(); await blocked;
    assert.equal(f.win.isDestroyed(), false);
    f.win.close(); assert.equal(f.requests, 1);
    f.quitting = true; f.guard.beginQuit(); f.guard.finishQuit();
    const closed = bounded(once(f.win, 'closed'), 'programmatic close');
    f.win.close(); await closed;
    assert.equal(f.dialogs.length, 0);
  });

  await check('real renderer crash offers one dialog and waits for cleanup before exit', async () => {
    const f = await fixture(); await f.crash();
    f.win.close(); f.win.close();
    assert.equal(f.dialogs.length, 1); assert.equal(f.requests, 0);
    f.dialogs[0].resolve({ response: 1 }); await tick();
    assert.equal(f.quitCalls, 1); assert.equal(f.win.isDestroyed(), false);
    const closed = bounded(once(f.win, 'closed'), 'post-cleanup close');
    f.guard.finishQuit(); await closed;
    assert.equal(f.errors.length, 0);
  });

  await check('real renderer hang recovers after an injected unresponsive signal', async () => {
    const f = await fixture(); await f.hang();
    // The renderer is actually blocked. Only OS hang-detection timing is injected.
    f.win.emit('unresponsive'); f.win.close();
    assert.equal(f.dialogs.length, 1);
    const loaded = bounded(once(f.contents, 'did-finish-load'), 'native recovery reload');
    f.dialogs[0].resolve({ response: 0 });
    try { await loaded; }
    catch (error) { throw new Error(`${error.message}; events=${f.events.join(',')}; errors=${f.errors.map(item => item.message).join(',')}`); }
    assert.equal(f.contents.isCrashed(), false); assert.equal(f.quitCalls, 0);
    assert.equal(await f.contents.executeJavaScript('21 * 2'), 42);
    f.win.close(); assert.equal(f.requests, 1); assert.equal(f.dialogs.length, 1);
    assert.equal(f.errors.length, 0);
    f.dispose();
  });

  await check('an independently recovered page ignores a stale native Quit result', async () => {
    const f = await fixture(); await f.crash(); f.win.close();
    const prompt = f.dialogs[0];
    const loaded = bounded(once(f.contents, 'did-finish-load'), 'external recovery');
    f.contents.reload(); await loaded;
    assert.equal(prompt.options.signal.aborted, true);
    prompt.resolve({ response: 1 }); await tick();
    assert.equal(f.quitCalls, 0); assert.equal(f.win.isDestroyed(), false);
    f.dispose();
  });

  await check('destroy aborts the pending dialog and ignores its later completion', async () => {
    const f = await fixture(); await f.crash(); f.win.close();
    const prompt = f.dialogs[0]; f.win.destroy();
    assert.equal(prompt.options.signal.aborted, true);
    prompt.resolve({ response: 1 }); await tick();
    assert.equal(f.quitCalls, 0);
  });

  await check('production before-quit hook awaits sidecar cleanup and handles repeated app.quit', async () => {
    const f = await fixture({ requestQuit: () => app.quit() }); await f.crash();
    const mainSource = readFileSync(path.join(__dirname, '..', 'main', 'main.js'), 'utf8');
    const marker = "app.on('before-quit', (event) => {";
    assert.notEqual(mainSource.lastIndexOf(marker), -1, 'production shutdown hook must be present');
    const calls = [];
    let releaseCleanup;
    const pendingCleanup = new Promise(resolve => { releaseCleanup = resolve; });
    const context = {
      app, mainWindowCloseGuard: f.guard, quitting: false, cleanupDone: false,
      log: { error: error => f.errors.push(error) },
      sidecar: { stop: async () => { calls.push('stop'); await pendingCleanup; calls.push('cleaned'); } },
    };
    // Run only the real shutdown handler. All other main-process startup stays out.
    runInNewContext(mainSource.slice(mainSource.lastIndexOf(marker)), context);
    const listener = app.listeners('before-quit').at(-1);
    const finished = bounded(new Promise(resolve => app.once('will-quit', event => {
      event.preventDefault(); resolve();
    })), 'production shutdown');
    f.win.close(); f.dialogs[0].resolve({ response: 1 }); await tick();
    assert.deepEqual(calls, ['stop']); assert.equal(f.win.isDestroyed(), false);
    f.win.close(); f.win.close();
    assert.equal(f.win.isDestroyed(), false, 'repeated close must wait for cleanup');
    app.quit(); assert.deepEqual(calls, ['stop'], 'repeated quit must share cleanup');
    releaseCleanup(); await finished;
    assert.deepEqual(calls, ['stop', 'cleaned']);
    assert.equal(context.cleanupDone, true); assert.equal(f.win.isDestroyed(), true);
    assert.equal(f.errors.length, 0);
    app.removeListener('before-quit', listener);
  });

  console.log(`ALL ${passed} WINDOW CLOSE CHECKS PASSED`);
  clearTimeout(watchdog);
  app.exit(0);
}).catch(error => {
  console.error('FAIL', error.stack || error);
  for (const win of owned) { if (!win.isDestroyed()) win.destroy(); }
  clearTimeout(watchdog);
  app.exit(1);
});

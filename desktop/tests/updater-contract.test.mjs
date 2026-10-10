import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import test from 'node:test';
import { createDesktopUpdater } from '../main/updater.js';

const require = createRequire(import.meta.url);
const { CancellationToken } = require('builder-util-runtime');
const tick = () => new Promise(setImmediate);

function fixture({ packaged = true, beforeInstall = async () => {} } = {}) {
  const source = new EventEmitter();
  const checks = [];
  const downloads = [];
  const installs = [];
  const states = [];
  source.checkForUpdates = () => {
    source.emit('checking-for-update');
    return new Promise((resolve) => checks.push(resolve));
  };
  source.downloadUpdate = (token = new CancellationToken()) => {
    downloads.push(token);
    return token.createPromise((_resolve, _reject, onCancel) => {
      onCancel(() => source.emit('update-cancelled'));
    });
  };
  source.quitAndInstall = (...args) => installs.push(args);
  const log = () => {};
  log.error = () => {};
  const updater = createDesktopUpdater({
    autoUpdater: source, packaged, version: '0.8.1-newui.1', beforeInstall, log,
    broadcast: (state) => states.push(state),
  });
  const offer = async () => {
    const checking = updater.check();
    await tick();
    source.emit('update-available', { version: '0.8.1-newui.2', releaseNotes: 'Notes' });
    checks.at(-1)({ cancellationToken: new CancellationToken() });
    await checking;
  };
  return { updater, source, checks, downloads, installs, states, offer };
}

test('development does not fetch or install application updates', async () => {
  const f = fixture({ packaged: false });
  assert.equal((await f.updater.check()).status, 'dev');
  assert.equal(f.checks.length, 0);
  await assert.rejects(f.updater.download());
  await assert.rejects(f.updater.install());
  assert.equal(f.installs.length, 0);
});

test('simultaneous checks use one updater request', async () => {
  const f = fixture();
  const first = f.updater.check();
  const second = f.updater.check();
  await tick();
  assert.equal(f.checks.length, 1);
  f.source.emit('update-not-available', { version: '0.8.1-newui.1' });
  f.checks[0]({});
  assert.equal((await first).status, 'latest');
  assert.equal((await second).status, 'latest');
});

test('install refuses an update that has not downloaded', async () => {
  let cleanup = 0;
  const f = fixture({ beforeInstall: async () => { cleanup += 1; } });
  await assert.rejects(f.updater.install());
  assert.equal(cleanup, 0);
  assert.equal(f.installs.length, 0);
});

test('install waits for backend cleanup and duplicate clicks do not reinstall', async () => {
  let finishCleanup;
  let cleanupCalls = 0;
  const cleanup = new Promise((resolve) => { finishCleanup = resolve; });
  const f = fixture({ beforeInstall: () => { cleanupCalls += 1; return cleanup; } });
  f.source.emit('update-downloaded', { version: '0.8.1-newui.2' });
  const first = f.updater.install();
  const second = f.updater.install();
  await tick();
  assert.equal(cleanupCalls, 1);
  assert.equal(f.installs.length, 0);
  finishCleanup();
  await Promise.all([first, second]);
  assert.deepEqual(f.installs, [[false, true]]);
});

test('cancel and retry use cancellable tokens for every download', async () => {
  const f = fixture();
  await f.offer();
  const first = f.updater.download();
  await tick();
  f.updater.cancel();
  assert.equal(f.downloads[0].cancelled, true);
  assert.equal((await first).status, 'available');
  const second = f.updater.download();
  await tick();
  assert.equal(f.downloads.length, 2);
  const retryToken = f.downloads[1];
  assert.notEqual(retryToken, f.downloads[0]);
  f.updater.cancel();
  const retryWasCancelled = retryToken.cancelled;
  if (!retryWasCancelled) retryToken.cancel();
  await second;
  assert.equal(retryWasCancelled, true, 'second download must also be cancellable');
  assert.equal(f.updater.state().status, 'available');
});

test('cancel before the download microtask starts cancels the same request', async () => {
  const f = fixture();
  await f.offer();
  const downloading = f.updater.download();
  f.updater.cancel();
  await tick();
  assert.equal(f.downloads.length, 1);
  const earlyTokenWasCancelled = f.downloads[0].cancelled;
  if (!earlyTokenWasCancelled) f.downloads[0].cancel();
  await downloading;
  assert.equal(earlyTokenWasCancelled, true);
  assert.equal(f.updater.state().status, 'available');
});

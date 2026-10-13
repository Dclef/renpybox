import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { createWindowCloseGuard } from '../main/window-close-guard.js';

const tick = () => new Promise(resolve => setImmediate(resolve));
const event = () => ({ defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } });
function fixture() {
  const contents = new EventEmitter();
  const win = new EventEmitter();
  const f = { win, contents, destroyed: false, crashed: false, blocked: false, quitting: false,
    quitCalls: 0, reloads: 0, crashes: 0, requests: [], dialogs: [], errors: [], locale: 'ZH' };
  win.webContents = contents;
  win.isDestroyed = contents.isDestroyed = () => f.destroyed;
  contents.isCrashed = () => f.crashed;
  contents.send = channel => f.requests.push(channel);
  contents.reload = () => { f.reloads += 1; };
  contents.forcefullyCrashRenderer = () => {
    f.crashes += 1; f.crashed = true; contents.emit('render-process-gone', {}, { reason: 'crashed' });
  };
  win.destroy = () => { if (f.destroyed) return; f.destroyed = true; win.emit('closed'); };
  win.close = () => {
    const closing = event(); win.emit('close', closing);
    if (closing.defaultPrevented) return;
    if (f.blocked) {
      const prevention = event(); contents.emit('will-prevent-unload', prevention);
      if (!prevention.defaultPrevented) return;
    }
    win.destroy();
  };
  f.guard = createWindowCloseGuard({ window: win,
    showMessageBox: (_owner, options) => new Promise((resolve, reject) => f.dialogs.push({ options, resolve, reject })),
    requestQuit: () => { f.quitCalls += 1; f.quitting = true; f.guard.beginQuit(); },
    isQuitting: () => f.quitting, getLocale: () => f.locale, log: error => f.errors.push(error),
  });
  f.recover = () => { f.crashed = false; contents.emit('did-finish-load'); };
  return f;
}

test('healthy closes stay in the renderer; only its confirmation allows closing', () => {
  const f = fixture();
  f.win.close(); f.win.close();
  assert.deepEqual(f.requests, ['window:close-requested', 'window:close-requested']);
  assert.equal(f.dialogs.length, 0);
  assert.equal(f.destroyed, false);
  f.guard.confirm();
  assert.equal(f.destroyed, true);
});

test('a renderer dirty/RPY beforeunload veto revokes an earlier confirmation', () => {
  const f = fixture(); f.blocked = true;
  f.guard.confirm();
  assert.equal(f.destroyed, false);
  f.win.close();
  assert.deepEqual(f.requests, ['window:close-requested']);
  assert.equal(f.dialogs.length, 0);
});

test('crash fallback is single-flight; cancel leaves the window open and permits retry', async () => {
  const f = fixture(); f.contents.forcefullyCrashRenderer();
  f.win.close(); f.win.close();
  assert.equal(f.dialogs.length, 1);
  assert.deepEqual(f.requests, []);
  assert.deepEqual(f.dialogs[0].options.buttons, ['重新加载界面', '退出程序', '取消']);
  f.dialogs[0].resolve({ response: 2 }); await tick();
  assert.equal(f.destroyed, false);
  f.locale = 'EN'; f.win.close();
  assert.equal(f.dialogs.length, 2);
  assert.deepEqual(f.dialogs[1].options.buttons, ['Reload interface', 'Quit', 'Cancel']);
  f.guard.dispose();
});

test('native quit enters application cleanup and destroys the crashed window only afterward', async () => {
  const f = fixture(); f.contents.forcefullyCrashRenderer(); f.win.close();
  f.dialogs[0].resolve({ response: 1 }); await tick();
  assert.equal(f.quitCalls, 1);
  assert.equal(f.destroyed, false, 'backend cleanup is still outstanding');
  f.guard.finishQuit();
  assert.equal(f.destroyed, true);
  assert.equal(f.quitCalls, 1);
});

test('reload terminates a hung renderer, then a loaded page regains normal close guards', async () => {
  const f = fixture(); f.win.emit('unresponsive'); f.win.close();
  f.dialogs[0].resolve({ response: 0 }); await tick();
  assert.equal(f.crashes, 1);
  assert.equal(f.reloads, 1);
  assert.equal(f.quitCalls, 0);
  f.recover(); f.win.close();
  assert.deepEqual(f.requests, ['window:close-requested']);
  assert.equal(f.dialogs.length, 1);
  f.guard.dispose();
});

test('already crashed renderer reload does not force a second crash', async () => {
  const f = fixture(); f.contents.forcefullyCrashRenderer(); f.win.close();
  f.dialogs[0].resolve({ response: 0 }); await tick();
  assert.equal(f.crashes, 1); assert.equal(f.reloads, 1);
  f.guard.dispose();
});

test('responsive event cancels fallback and ignores its late Quit result', async () => {
  const f = fixture(); f.win.emit('unresponsive'); f.win.close();
  const prompt = f.dialogs[0]; f.win.emit('responsive');
  assert.equal(prompt.options.signal.aborted, true);
  prompt.resolve({ response: 1 }); await tick();
  assert.equal(f.quitCalls, 0);
  f.win.close();
  assert.deepEqual(f.requests, ['window:close-requested']);
  f.guard.dispose();
});

test('recovered page cancels an old crash dialog and cannot be reloaded by its stale result', async () => {
  const f = fixture(); f.contents.forcefullyCrashRenderer(); f.win.close();
  const prompt = f.dialogs[0]; f.recover();
  assert.equal(prompt.options.signal.aborted, true);
  prompt.resolve({ response: 0 }); await tick();
  assert.equal(f.reloads, 0); assert.equal(f.quitCalls, 0);
  f.guard.dispose();
});

test('destroy disposes listeners, cancels native dialog and ignores later completion', async () => {
  const f = fixture(); f.win.emit('unresponsive'); f.win.close();
  const prompt = f.dialogs[0]; f.win.destroy();
  assert.equal(prompt.options.signal.aborted, true);
  prompt.resolve({ response: 1 }); await tick();
  assert.equal(f.quitCalls, 0);
  for (const name of ['close', 'closed', 'responsive', 'unresponsive']) assert.equal(f.win.listenerCount(name), 0);
  for (const name of ['render-process-gone', 'did-finish-load', 'will-prevent-unload']) assert.equal(f.contents.listenerCount(name), 0);
  f.guard.dispose();
});

test('committed programmatic quit bypasses the dirty barrier after cleanup, without prompting', () => {
  const f = fixture(); f.blocked = true; f.quitting = true;
  f.guard.beginQuit(); f.guard.finishQuit(); f.win.close();
  assert.equal(f.destroyed, true);
  assert.equal(f.dialogs.length, 0); assert.deepEqual(f.requests, []);
});

test('programmatic quit invalidates native dialog; a hung window survives until cleanup completes', async () => {
  const f = fixture(); f.win.emit('unresponsive'); f.win.close();
  const prompt = f.dialogs[0]; f.quitting = true; f.guard.beginQuit();
  assert.equal(prompt.options.signal.aborted, true);
  prompt.resolve({ response: 0 }); await tick();
  assert.equal(f.reloads, 0); assert.equal(f.destroyed, false);
  f.guard.finishQuit(); assert.equal(f.destroyed, true);
});

test('a renderer that hangs during final app.quit can still be destroyed', () => {
  const f = fixture(); f.quitting = true; f.guard.beginQuit(); f.guard.finishQuit();
  assert.equal(f.destroyed, false);
  f.win.emit('unresponsive'); assert.equal(f.destroyed, true);
});

test('dialog failure is logged and the next close can retry without an unhandled rejection', async () => {
  const f = fixture(); f.contents.forcefullyCrashRenderer(); f.win.close();
  f.dialogs[0].reject(new Error('Dialog unavailable')); await tick();
  assert.equal(f.errors[0].message, 'Dialog unavailable');
  f.win.close(); assert.equal(f.dialogs.length, 2);
  f.guard.dispose();
});

test('IPC send failure enters fallback instead of throwing from a close event', () => {
  const f = fixture(); f.contents.send = () => { throw new Error('Render frame disposed'); };
  assert.doesNotThrow(() => f.win.close());
  assert.equal(f.dialogs.length, 1); assert.equal(f.destroyed, false);
  f.guard.dispose();
});

test('recovery waits for an asynchronous renderer exit before reloading', async () => {
  const f = fixture();
  f.contents.forcefullyCrashRenderer = () => { f.crashes += 1; };
  f.win.emit('unresponsive'); f.win.close();
  f.dialogs[0].resolve({ response: 0 }); await tick();
  assert.equal(f.crashes, 1); assert.equal(f.reloads, 0);
  f.crashed = true; f.contents.emit('render-process-gone', {}, { reason: 'crashed' }); await tick();
  assert.equal(f.reloads, 1);
  f.guard.dispose();
});

test('shutdown cancels a recovery still waiting for renderer exit', async () => {
  const f = fixture();
  f.contents.forcefullyCrashRenderer = () => { f.crashes += 1; };
  f.win.emit('unresponsive'); f.win.close();
  f.dialogs[0].resolve({ response: 0 }); await tick();
  f.quitting = true; f.guard.beginQuit();
  f.crashed = true; f.contents.emit('render-process-gone', {}, { reason: 'crashed' }); await tick();
  assert.equal(f.reloads, 0); assert.equal(f.destroyed, false);
  f.guard.finishQuit(); assert.equal(f.destroyed, true);
});

test('repeated closes stay blocked until application cleanup finishes', async () => {
  for (const crashed of [false, true]) {
    const f = fixture();
    if (crashed) f.contents.forcefullyCrashRenderer();
    f.quitting = true; f.guard.beginQuit();
    f.win.close(); f.win.close();
    assert.equal(f.destroyed, false, 'a second close cannot bypass pending cleanup');
    assert.equal(f.dialogs.length, 0); assert.deepEqual(f.requests, []);
    f.guard.finishQuit();
    if (!crashed) f.win.close();
    assert.equal(f.destroyed, true);
  }
});

test('destroyed webContents can quit through native fallback without sending IPC', async () => {
  const f = fixture(); f.contents.isDestroyed = () => true;
  f.contents.send = () => { throw new Error('must not send to destroyed contents'); };
  f.contents.isCrashed = () => { throw new Error('must not inspect destroyed contents'); };
  assert.doesNotThrow(() => f.win.close());
  assert.equal(f.dialogs.length, 1);
  f.dialogs[0].resolve({ response: 1 }); await tick();
  assert.equal(f.quitCalls, 1); assert.equal(f.destroyed, false);
  f.win.close(); assert.equal(f.destroyed, false);
  f.guard.finishQuit(); assert.equal(f.destroyed, true);
  assert.deepEqual(f.errors, []);
});

test('a late renderer confirmation cannot bypass an active native recovery decision', () => {
  const f = fixture(); f.win.emit('unresponsive'); f.win.close(); f.guard.confirm();
  assert.equal(f.destroyed, false); assert.equal(f.quitCalls, 0);
  f.guard.dispose();
});

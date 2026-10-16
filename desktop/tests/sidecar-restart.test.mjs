/**
 * Regression: backend crashes during the INITIAL startOnce (never becomes healthy).
 *
 * Mock pitfalls (do not "fix" by reintroducing these):
 * 1. spawn must emit exit asynchronously — sync emit races before the exit listener attaches.
 * 2. failHealth must start true — an instant healthy fetch makes waitHealthy win before the crash.
 */
import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import { EventEmitter } from 'node:events';
import { syncBuiltinESMExports } from 'node:module';
import path from 'node:path';
import { PassThrough } from 'node:stream';
import test from 'node:test';
import { Sidecar } from '../main/sidecar.js';

const expectedVersion = '0.8.1';
const appRoot = path.resolve('test-sidecar-restart-user-data');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function build(t, state) {
  const logs = [];
  const spawned = [];
  const children = [];
  const oldExternal = process.env.RENPYBOX_SIDECAR_EXTERNAL;
  delete process.env.RENPYBOX_SIDECAR_EXTERNAL;

  const sidecar = new Sidecar({
    backendExecutable: process.execPath,
    appRoot,
    expectedAppVersion: expectedVersion,
    onLog: (line) => logs.push(line),
  });

  t.mock.method(childProcess, 'spawn', (command) => {
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.pid = 54321 + children.length;
    child.kill = () => { setImmediate(() => child.emit('exit', 0, null)); return true; };
    if (command === 'taskkill' || command === 'kill') {
      setImmediate(() => child.emit('exit', 0, null));
    } else {
      spawned.push({ command });
      children.push(child);
      state.alive = child;
      if (state.crashOnSpawn) setImmediate(() => state.crashOnSpawn(child));
    }
    return child;
  });
  syncBuiltinESMExports();

  t.after(async () => {
    await sidecar.stop();
    for (const child of children) { child.stdout.destroy(); child.stderr.destroy(); }
    t.mock.restoreAll();
    syncBuiltinESMExports();
    if (oldExternal === undefined) delete process.env.RENPYBOX_SIDECAR_EXTERNAL;
    else process.env.RENPYBOX_SIDECAR_EXTERNAL = oldExternal;
  });

  t.mock.method(globalThis, 'fetch', async () => {
    if (state.failHealth || !state.alive) {
      throw new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } });
    }
    const child = state.alive;
    return {
      ok: true,
      json: async () => ({
        ok: true, mode: 'api', app_version: expectedVersion,
        pid: child.pid, config_path: path.join(appRoot, 'config.json'),
      }),
    };
  });

  return { sidecar, logs, spawned, children };
}

test('initial startup crash keeps auto-restart alive and does not latch stopping', async (t) => {
  const state = { alive: null, failHealth: true, crashOnSpawn: null };
  const f = build(t, state);
  state.crashOnSpawn = (child) => {
    state.alive = null;
    child.emit('exit', 1, null);
  };

  // 后端一直崩：start() 自己按 MAX_RESTARTS 重试到预算耗尽才 reject。
  await assert.rejects(f.sidecar.start(), /Python 后端退出/);
  assert.equal(f.sidecar.stopping, false, 'startup failure must not latch stopping');
  assert.ok(f.logs.some((line) => /后第 1 次重启/.test(line)), 'restart must be announced');
  assert.equal(f.spawned.length, 4, 'initial attempt + 3 retries');

  // 后端修好：不需要显式 restart()，下一次 start() 必须能恢复。
  state.crashOnSpawn = null;
  state.failHealth = false;
  await sleep(200);
  const info = await f.sidecar.start();
  assert.equal(info.pid, f.children[f.children.length - 1].pid);
  assert.equal(f.sidecar.stopping, false);
});

test('startup crash loop stops at the restart budget instead of retrying forever', async (t) => {
  const state = { alive: null, failHealth: true, crashOnSpawn: null };
  const f = build(t, state);
  state.crashOnSpawn = (child) => {
    state.alive = null;
    child.emit('exit', 1, null);
  };

  await assert.rejects(f.sidecar.start(), /Python 后端退出/);
  assert.equal(f.spawned.length, 4, `must give up after MAX_RESTARTS, spawns=${f.spawned.length}`);
  assert.ok(f.logs.some((line) => /超过重启上限/.test(line)), 'must report giving up');
  await sleep(2500);
  assert.equal(f.spawned.length, 4, 'no further spawns after the budget is exhausted');
});

test('a failed start does not spend the budget of the next real crash', async (t) => {
  const state = { alive: null, failHealth: true, crashOnSpawn: null };
  const f = build(t, state);
  state.crashOnSpawn = (child) => {
    state.alive = null;
    child.emit('exit', 1, null);
  };
  await assert.rejects(f.sidecar.start(), /Python 后端退出/);

  // 恢复后成功启动一次，崩溃预算应清零。
  state.crashOnSpawn = null;
  state.failHealth = false;
  await sleep(100);
  await f.sidecar.start();
  assert.equal(f.sidecar.restarts, 0, 'a healthy start must clear the crash budget');
});

test('a backend crash after startup still auto-restarts through the exit handler', async (t) => {
  const state = { alive: null, failHealth: false, crashOnSpawn: null };
  const f = build(t, state);
  const info = await f.sidecar.start();
  assert.equal(f.spawned.length, 1);
  assert.equal(info.pid, f.children[0].pid);

  // 运行期崩溃（startPromise 已结算、starting=false）：走退出处理器的排期路径。
  state.alive = null;
  f.children[0].emit('exit', 1, null);
  assert.ok(f.logs.some((line) => /后第 1 次重启/.test(line)), 'runtime crash must be announced');
  await sleep(1200);
  assert.equal(f.spawned.length, 2, `runtime crash must respawn, spawns=${f.spawned.length}`);
});

test('stop() supersedes an in-flight startup crash retry loop', async (t) => {
  const state = { alive: null, failHealth: true, crashOnSpawn: null };
  const f = build(t, state);
  state.crashOnSpawn = (child) => {
    state.alive = null;
    child.emit('exit', 1, null);
  };

  const starting = f.sidecar.start();
  const settled = assert.rejects(starting);
  await sleep(50);
  const spawnsBeforeStop = f.spawned.length;
  await f.sidecar.stop();
  await settled;
  assert.ok(spawnsBeforeStop >= 1, 'the first attempt must have spawned');
  await sleep(2500);
  assert.equal(f.spawned.length, spawnsBeforeStop, 'stop() must abort the remaining retries');
});

test('restart() waits for a failing startup attempt and then starts a fresh one', async (t) => {
  const state = { alive: null, failHealth: true, crashOnSpawn: null };
  const f = build(t, state);
  state.crashOnSpawn = (child) => {
    state.alive = null;
    child.emit('exit', 1, null);
  };

  const starting = f.sidecar.start();
  const settled = assert.rejects(starting);
  await sleep(50);

  // 修好后端后调用 restart()：它必须等旧的重试链收尾，再返回一个真正健康的实例。
  state.crashOnSpawn = null;
  state.failHealth = false;
  const info = await f.sidecar.restart();
  await settled;
  assert.equal(info.pid, f.children[f.children.length - 1].pid);
  assert.equal(f.sidecar.stopping, false);
});

test('waitHealthy never accepts a health response from the process that just exited', async (t) => {
  const logs = [];
  const children = [];
  const oldExternal = process.env.RENPYBOX_SIDECAR_EXTERNAL;
  delete process.env.RENPYBOX_SIDECAR_EXTERNAL;
  const sidecar = new Sidecar({
    backendExecutable: process.execPath,
    appRoot,
    expectedAppVersion: expectedVersion,
    onLog: (line) => logs.push(line),
  });

  let phase = 'reuse';
  let resolveSlowFetch = null;
  let childRef = null;
  let stalePayloadPid = null;
  let staleServed = false;

  t.mock.method(childProcess, 'spawn', (command) => {
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.pid = 77777 + children.length;
    child.kill = () => { setImmediate(() => child.emit('exit', 0, null)); return true; };
    if (command === 'taskkill' || command === 'kill') {
      setImmediate(() => child.emit('exit', 0, null));
    } else {
      children.push(child);
      childRef = child;
    }
    return child;
  });
  syncBuiltinESMExports();

  const payloadFor = (pid) => ({
    ok: true,
    json: async () => ({
      ok: true, mode: 'api', app_version: expectedVersion,
      pid, config_path: path.join(appRoot, 'config.json'),
    }),
  });

  t.mock.method(globalThis, 'fetch', async () => {
    if (phase === 'reuse') {
      phase = 'in-flight';
      throw new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } });
    }
    if (phase === 'in-flight') {
      phase = 'retry';
      const deadPid = childRef.pid;
      await new Promise((resolve) => { resolveSlowFetch = resolve; });
      // 已经退出那个进程留下的最后一个 200：绝不能当成健康结果返回给调用方。
      stalePayloadPid = deadPid;
      staleServed = true;
      return payloadFor(deadPid);
    }
    // 重试后新起的后端：这次是健康结果。
    return payloadFor(children[children.length - 1].pid);
  });

  t.after(async () => {
    await sidecar.stop();
    for (const child of children) { child.stdout.destroy(); child.stderr.destroy(); }
    t.mock.restoreAll();
    syncBuiltinESMExports();
    if (oldExternal === undefined) delete process.env.RENPYBOX_SIDECAR_EXTERNAL;
    else process.env.RENPYBOX_SIDECAR_EXTERNAL = oldExternal;
  });

  const starting = sidecar.start();
  for (let i = 0; i < 50 && !resolveSlowFetch; i += 1) await sleep(20);
  assert.ok(resolveSlowFetch, 'health probe should be in flight');
  childRef.emit('exit', 1, null);
  resolveSlowFetch();
  const info = await starting;
  assert.ok(staleServed, 'the stale response must have been produced');
  assert.notEqual(info.pid, stalePayloadPid, 'a health response from the dead process must never be accepted');
  assert.equal(info.pid, children[children.length - 1].pid);
  assert.equal(children.length, 2, 'the startup crash must trigger a retry');
});

import assert from 'node:assert/strict';
import childProcess from 'node:child_process';
import { EventEmitter } from 'node:events';
import { syncBuiltinESMExports } from 'node:module';
import path from 'node:path';
import { PassThrough } from 'node:stream';
import test from 'node:test';
import { Sidecar } from '../main/sidecar.js';

const expectedVersion = '0.8.1';
const appRoot = path.resolve('test-sidecar-user-data');
const health = (overrides = {}) => ({
  ok: true, mode: 'api', app_version: expectedVersion, pid: 54321,
  config_path: path.join(appRoot, 'config.json'), python_version: '3.10.11',
  ...overrides,
});

function fixture(t, options = {}) {
  const logs = [];
  const spawned = [];
  const children = [];
  const oldExternal = process.env.RENPYBOX_SIDECAR_EXTERNAL;
  delete process.env.RENPYBOX_SIDECAR_EXTERNAL;
  const sidecar = new Sidecar({
    backendExecutable: process.execPath, appRoot, expectedAppVersion: expectedVersion,
    onLog: (line) => logs.push(line), ...options,
  });
  t.mock.method(childProcess, 'spawn', (command, args, spawnOptions) => {
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.pid = 54321 + children.length;
    child.kill = () => { queueMicrotask(() => child.emit('exit', 0, null)); return true; };
    if (command === 'taskkill' || command === 'kill') {
      queueMicrotask(() => child.emit('exit', 0, null));
    } else {
      spawned.push({ command, args, spawnOptions });
      children.push(child);
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
  return { sidecar, logs, spawned, children };
}

function mockHealth(t, read) {
  t.mock.method(globalThis, 'fetch', async () => {
    const payload = read();
    if (!payload) throw new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } });
    return { ok: true, json: async () => payload };
  });
}

test('development may reuse compatible backend without taking ownership', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => health());
  assert.equal((await f.sidecar.start()).pid, 54321);
  assert.equal(f.spawned.length, 0);
  assert.equal(f.sidecar.owned, false);
});

test('packaged backend refuses an occupied healthy backend instead of reusing it', async (t) => {
  const f = fixture(t, { allowReuse: false });
  mockHealth(t, () => health());
  await assert.rejects(f.sidecar.start());
  assert.equal(f.spawned.length, 0);
  assert.equal(f.sidecar.owned, false);
});

test('backend of another version is not silently reused', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => health({ app_version: '0.0.1' }));
  await assert.rejects(f.sidecar.start());
  assert.equal(f.spawned.length, 0);
});

test('backend with a different configuration directory is not silently reused', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => health({ config_path: path.resolve('other-user', 'config.json') }));
  await assert.rejects(f.sidecar.start());
  assert.equal(f.spawned.length, 0);
});

test('concurrent starts spawn one backend and use the owned process identity', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => f.children.length ? health({ pid: f.children[0].pid }) : null);
  const results = await Promise.all([f.sidecar.start(), f.sidecar.start()]);
  assert.equal(f.spawned.length, 1);
  assert.equal(results[0].pid, f.children[0].pid);
  assert.equal(results[1].pid, f.children[0].pid);
  assert.equal(f.sidecar.owned, true);
});

test('starting an already owned backend does not spawn again', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => f.children.length ? health({ pid: f.children[0].pid }) : null);
  const first = await f.sidecar.start();
  const second = await f.sidecar.start();
  assert.equal(f.spawned.length, 1);
  assert.equal(first.pid, second.pid);
});

test('packaged launch runs bundled executable with isolated Python paths and user data', async (t) => {
  const f = fixture(t, { allowReuse: false });
  mockHealth(t, () => f.children.length ? health({ pid: f.children[0].pid }) : null);
  await f.sidecar.start();
  const launch = f.spawned[0];
  assert.equal(launch.command, process.execPath);
  assert.deepEqual(launch.args, []);
  assert.equal(launch.spawnOptions.cwd, appRoot);
  assert.equal(launch.spawnOptions.windowsHide, true);
  assert.equal(launch.spawnOptions.env.RENPYBOX_APP_ROOT, appRoot);
  assert.equal(launch.spawnOptions.env.PYTHONPATH, '');
  assert.equal(launch.spawnOptions.env.PYTHONHOME, '');
});

test('missing bundled backend fails clearly without spawning system Python', async (t) => {
  const f = fixture(t, { backendExecutable: path.resolve('missing-backend-test-file.exe') });
  mockHealth(t, () => null);
  await assert.rejects(f.sidecar.start());
  assert.equal(f.spawned.length, 0);
});

test('stop during initial health probe prevents a later backend spawn', async (t) => {
  const f = fixture(t);
  let refuseProbe;
  t.mock.method(globalThis, 'fetch', () => new Promise((_resolve, reject) => { refuseProbe = reject; }));
  const starting = f.sidecar.start();
  const failedStart = assert.rejects(starting);
  await f.sidecar.stop();
  refuseProbe(new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } }));
  await failedStart;
  assert.equal(f.spawned.length, 0);
});

test('owned startup rejects another process answering health on the port', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => f.children.length ? health({ pid: 99999 }) : null);
  await assert.rejects(f.sidecar.start());
  assert.equal(f.spawned.length, 1);
});

test('backend output retains every line and UTF-8 across data chunks', async (t) => {
  const f = fixture(t);
  mockHealth(t, () => f.children.length ? health({ pid: f.children[0].pid }) : null);
  await f.sidecar.start();
  f.logs.length = 0;
  const child = f.children[0];
  const lines = Array.from({ length: 20 }, (_, i) => 'audit-line-' + i);
  child.stdout.write(lines.join(String.fromCharCode(10)) + String.fromCharCode(10));
  const unicode = Buffer.from('完整中文日志' + String.fromCharCode(10), 'utf8');
  child.stderr.write(unicode.subarray(0, 1));
  child.stderr.write(unicode.subarray(1, 7));
  child.stderr.write(unicode.subarray(7));
  await new Promise(setImmediate);
  for (const line of lines) assert.ok(f.logs.some((entry) => entry.endsWith(line)), 'missing ' + line);
  assert.ok(f.logs.some((entry) => entry.endsWith('完整中文日志')));
  assert.ok(f.logs.every((entry) => !entry.includes('�')));
});

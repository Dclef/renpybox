import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

function fixture(t, { vite = false, electron } = {}) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'renpybox-dev-startup-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(path.join(root, 'scripts'));
  mkdirSync(path.join(root, 'main'));
  writeFileSync(path.join(root, 'package.json'), '{"type":"module"}', 'utf8');
  copyFileSync(new URL('../scripts/dev.mjs', import.meta.url), path.join(root, 'scripts', 'dev.mjs'));
  copyFileSync(new URL('../main/stdio-console.js', import.meta.url), path.join(root, 'main', 'stdio-console.js'));
  // 标记启动边界，禁止测试真的启动 Python、Vite 或 Electron。
  writeFileSync(path.join(root, 'main', 'sidecar.js'), `
    export class Sidecar {
      async start() {
        console.log('SIDECAR_STARTED');
        throw new Error('测试停止在后端启动边界');
      }
      async stop() {}
    }
  `, 'utf8');
  if (vite) {
    const bin = path.join(root, 'node_modules', 'vite', 'bin');
    mkdirSync(bin, { recursive: true });
    writeFileSync(path.join(bin, 'vite.js'), '', 'utf8');
  }
  if (electron !== undefined) {
    const pkg = path.join(root, 'node_modules', 'electron');
    mkdirSync(pkg, { recursive: true });
    writeFileSync(path.join(pkg, 'package.json'), '{"main":"index.cjs"}', 'utf8');
    writeFileSync(path.join(pkg, 'index.cjs'), electron, 'utf8');
  }
  return (...args) => {
    const result = spawnSync(process.execPath, [path.join(root, 'scripts', 'dev.mjs'), ...args], {
      cwd: root, encoding: 'utf8', timeout: 10_000, windowsHide: true,
      env: { ...process.env, NODE_PATH: '' },
    });
    assert.ifError(result.error);
    assert.equal(result.status, 1);
    return result.stdout + result.stderr;
  };
}

for (const args of [[], ['--web']]) {
  test(`missing Vite stops before sidecar (${args[0] || 'desktop'})`, (t) => {
    const output = fixture(t)(...args);
    assert.match(output, /Vite.*npm ci --include=dev/);
    assert.doesNotMatch(output, /SIDECAR_STARTED/);
  });
}

test('missing Electron package stops before sidecar with dependency repair command', (t) => {
  const output = fixture(t, { vite: true })();
  assert.match(output, /npm ci --include=dev/);
  assert.doesNotMatch(output, /SIDECAR_STARTED/);
});

for (const electron of [
  'throw new Error("Electron failed to install correctly");',
  'module.exports = __dirname + "/missing-electron.exe";',
  'module.exports = {};',
]) {
  test(`broken Electron runtime stops before sidecar: ${electron}`, (t) => {
    const output = fixture(t, { vite: true, electron })();
    assert.match(output, /node node_modules\/electron\/install\.js/);
    assert.doesNotMatch(output, /SIDECAR_STARTED/);
  });
}

test('web mode starts sidecar without Electron', (t) => {
  const output = fixture(t, { vite: true })('--web');
  assert.match(output, /SIDECAR_STARTED/);
  assert.doesNotMatch(output, /Electron 运行时不可用/);
});

test('desktop mode resolves an available Electron runtime through its package entry', (t) => {
  const output = fixture(t, { vite: true, electron: 'module.exports = process.execPath;' })();
  assert.match(output, /SIDECAR_STARTED/);
  assert.doesNotMatch(output, /Electron 运行时不可用/);
});

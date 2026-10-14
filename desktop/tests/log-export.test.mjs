/**
 * 运行日志导出 / 定位的纯逻辑测试，外加壳页与 IPC 通道的接线守卫。
 *
 * 接线守卫用文本断言，是因为壳窗口（shell/welcome.html + welcome.js）跑在独立
 * BrowserWindow 里，不参与渲染端测试套件；通道名写错在真机上只会表现为
 * 「日志接口不可用」，所以用最小代价把它钉在测试里。
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  LOG_SOURCES,
  exportFilename,
  logRevealTarget,
  resolveLogFile,
  writeLogExport,
} from '../main/log-export.js';

const DESKTOP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function withTempDir(run) {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'renpybox-log-'));
  try {
    return await run(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test('日志来源映射固定为 app.log / desktop.log，未知来源抛错', () => {
  assert.deepEqual(LOG_SOURCES, { app: 'app.log', desktop: 'desktop.log' });
  assert.equal(resolveLogFile('C:/logs', 'app'), path.join('C:/logs', 'app.log'));
  assert.equal(resolveLogFile('C:/logs', 'desktop'), path.join('C:/logs', 'desktop.log'));
  assert.throws(() => resolveLogFile('C:/logs', 'other'), /未知日志类型/);
});

test('导出文件名带来源与时间戳', () => {
  const now = new Date(2026, 9, 12, 21, 5, 7);
  assert.equal(exportFilename('app', now), 'renpybox-app-20261012-210507.log');
  assert.equal(exportFilename('desktop', now), 'renpybox-desktop-20261012-210507.log');
});

test('日志文件存在时导出整份文件，而不是界面上的截断尾巴', async () => {
  await withTempDir(async (dir) => {
    const logDirectory = path.join(dir, 'log');
    await writeFile(path.join(dir, 'ignored.txt'), '', 'utf8').catch(() => {});
    const { mkdir } = await import('node:fs/promises');
    await mkdir(logDirectory, { recursive: true });
    const full = 'line 1\nline 2\nline 3\n';
    await writeFile(path.join(logDirectory, 'app.log'), full, 'utf8');
    const destination = path.join(dir, 'out', 'export.log');
    const result = await writeLogExport({ source: 'app', logDirectory, destination, snapshot: 'tail only' });
    assert.equal(result.written, true);
    assert.equal(result.bytes, Buffer.byteLength(full, 'utf8'));
    assert.equal(await readFile(destination, 'utf8'), full);
  });
});

test('日志文件还没生成时退化为导出界面快照', async () => {
  await withTempDir(async (dir) => {
    const logDirectory = path.join(dir, 'log');
    const destination = path.join(dir, 'out', 'export.log');
    const result = await writeLogExport({ source: 'desktop', logDirectory, destination, snapshot: '正在读取日志…' });
    assert.equal(result.written, true);
    assert.equal(await readFile(destination, 'utf8'), '正在读取日志…');
  });
});

test('文件与快照都没有内容时不写空文件', async () => {
  await withTempDir(async (dir) => {
    const logDirectory = path.join(dir, 'log');
    const destination = path.join(dir, 'out', 'export.log');
    const result = await writeLogExport({ source: 'app', logDirectory, destination, snapshot: '' });
    assert.equal(result.written, false);
    assert.equal(result.bytes, 0);
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(dir), []);
  });
});

test('打开日志：文件存在定位文件，缺失时退回日志目录', async () => {
  await withTempDir(async (dir) => {
    const logDirectory = path.join(dir, 'log');
    const missing = await logRevealTarget(logDirectory, 'app');
    assert.equal(missing.kind, 'directory');
    assert.equal(missing.path, logDirectory);

    const { mkdir } = await import('node:fs/promises');
    await mkdir(logDirectory, { recursive: true });
    await writeFile(path.join(logDirectory, 'app.log'), 'x', 'utf8');
    const found = await logRevealTarget(logDirectory, 'app');
    assert.equal(found.kind, 'file');
    assert.equal(found.path, path.join(logDirectory, 'app.log'));
  });
});

test('壳页接线：按钮 id、bridge 方法与 IPC 通道三方一致', async () => {
  const html = await readFile(path.join(DESKTOP_ROOT, 'shell', 'welcome.html'), 'utf8');
  const shell = await readFile(path.join(DESKTOP_ROOT, 'shell', 'welcome.js'), 'utf8');
  const preload = await readFile(path.join(DESKTOP_ROOT, 'main', 'preload-shell.cjs'), 'utf8');
  const main = await readFile(path.join(DESKTOP_ROOT, 'main', 'main.js'), 'utf8');

  assert.match(html, /id="export"[^>]*>导出日志</, 'welcome.html 需要有 导出日志 按钮');
  assert.match(html, /id="reveal"[^>]*>打开日志</, 'welcome.html 需要有 打开日志 按钮');
  assert.match(shell, /\$\('export'\)\)?\.addEventListener|exportButton\.addEventListener/, 'welcome.js 要绑定导出按钮');
  assert.match(shell, /revealButton\.addEventListener/, 'welcome.js 要绑定打开日志按钮');
  assert.match(shell, /bridge\.logs\.export\(/, 'welcome.js 要调用 bridge.logs.export');
  assert.match(shell, /bridge\.logs\.reveal\(/, 'welcome.js 要调用 bridge.logs.reveal');
  assert.match(preload, /ipcRenderer\.invoke\('app:export-logs'/, 'preload 要暴露 app:export-logs');
  assert.match(preload, /ipcRenderer\.invoke\('app:reveal-logs'/, 'preload 要暴露 app:reveal-logs');
  assert.match(main, /ipcMain\.handle\('app:export-logs'/, 'main.js 要处理 app:export-logs');
  assert.match(main, /ipcMain\.handle\('app:reveal-logs'/, 'main.js 要处理 app:reveal-logs');
});

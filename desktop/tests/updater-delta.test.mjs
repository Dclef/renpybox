import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { createDesktopUpdater } from '../main/updater.js';
import { deltaAssetName, selectDeltaAsset, spawnDeltaApplier } from '../main/updater-delta.js';

const installer = version => ({
  name: `RenpyBox-${version}-x64.exe`,
  size: 280000000,
  digest: `sha256:${'ab'.repeat(32)}`,
  browser_download_url: `https://example.test/renpybox/RenpyBox-${version}-x64.exe`,
});
const delta = (version, base, extra = {}) => ({
  name: `RenpyBox-${version}-from-${base}-x64.delta.zip`,
  size: 1200,
  digest: `sha256:${'cd'.repeat(32)}`,
  browser_download_url: `https://example.test/renpybox/RenpyBox-${version}-from-${base}-x64.delta.zip`,
  ...extra,
});
const release = (version, assets, extra = {}) => ({
  tag_name: `v${version}`,
  draft: false,
  prerelease: false,
  html_url: `https://example.test/v${version}`,
  body: 'notes',
  assets,
  ...extra,
});

test('增量包文件名必须带基线版本', () => {
  assert.equal(deltaAssetName('0.9.2', '0.9.1'), 'renpybox-0.9.2-from-0.9.1-x64.delta.zip');
});

test('selectDeltaAsset 只挑基线等于当前版本的增量包，且忽略大小写', () => {
  const current = { currentVersion: '0.9.1' };
  const asset = delta('0.9.2', '0.9.1', { name: 'renpybox-0.9.2-from-0.9.1-x64.DELTA.zip' });
  assert.equal(selectDeltaAsset(release('0.9.2', [installer('0.9.2'), asset]), current), asset);
  // 干净安装跳过 0.9.1 时必须走全量：基线对不上就当作没有增量包
  const basedOn091 = delta('0.9.2', '0.9.1');
  assert.equal(selectDeltaAsset(release('0.9.2', [basedOn091]), { currentVersion: '0.9.0' }), null,
    '0.9.0 用户不能拿到基于 0.9.1 生成的增量包');
  assert.equal(selectDeltaAsset(release('0.9.2', [basedOn091]), current), basedOn091);
  assert.equal(selectDeltaAsset(release('0.9.1', [delta('0.9.1', '0.9.0')]), current), null);
  assert.equal(selectDeltaAsset(release('0.9.2', [delta('0.9.2', '0.9.1', { size: 0 })]), current), null);
  assert.equal(selectDeltaAsset(release('0.9.2', [delta('0.9.3', '0.9.1')]), current), null, '文件名版本必须等于发布版本');
});

test('spawnDeltaApplier 复制 exe 与脚本，并用 node 模式拉起，同时清掉旧副本', async () => {
  const tempDir = await mkdtemp(path.join(os.tmpdir(), 'renpybox-delta-'));
  const copies = [];
  const spawned = [];
  const removed = [];
  const listed = [];
  let unrefed = false;
  const result = await spawnDeltaApplier({
    electronExe: 'C:\\RenpyBox\\RenpyBox.exe',
    scriptPath: 'C:\\app\\update-apply.mjs',
    patchPath: 'C:\\tmp\\patch.zip',
    installDir: 'C:\\RenpyBox',
    appExe: 'C:\\RenpyBox\\RenpyBox.exe',
    pid: 42,
    baseVersion: '0.9.1',
    relaunch: true,
    tempDir,
    now: () => 1000,
    copyFile: async (from, to) => { copies.push([from, to]); },
    readdir: async () => { listed.push(true); return ['RenpyBoxUpdate_1_2.exe', 'update-apply.mjs', 'RenpyBox-0.9.2-x64.delta.zip']; },
    rm: async (target, options) => { removed.push([target, options]); },
    spawn: (exe, args, options) => {
      spawned.push({ exe, args, options });
      return {
        unref() { unrefed = true; },
        once(event, fn) { if (event === 'spawn') queueMicrotask(fn); },
      };
    },
  });
  assert.equal(copies.length, 2);
  assert.equal(copies[0][0], 'C:\\RenpyBox\\RenpyBox.exe');
  assert.equal(copies[1][0], 'C:\\app\\update-apply.mjs');
  assert.match(result.copiedExe, /RenpyBoxUpdate_42_1000\.exe$/);
  // 旧的应用器副本会被删掉，避免每次更新在 userData 里留一个 240MB 的 exe
  assert.deepEqual(removed.map(([target]) => path.basename(target)), ['RenpyBoxUpdate_1_2.exe']);
  assert.equal(spawned[0].exe, result.copiedExe);
  assert.deepEqual(spawned[0].args.slice(1), [
    '--patch', 'C:\\tmp\\patch.zip',
    '--install-dir', 'C:\\RenpyBox',
    '--app-exe', 'C:\\RenpyBox\\RenpyBox.exe',
    '--pid', '42',
    '--base-version', '0.9.1',
    '--relaunch', '1',
  ]);
  assert.equal(spawned[0].args[0], copies[1][1]);
  assert.equal(spawned[0].options.detached, true);
  assert.equal(spawned[0].options.stdio, 'ignore');
  assert.equal(spawned[0].options.env.ELECTRON_RUN_AS_NODE, '1');
  assert.equal(unrefed, true);
  await rm(tempDir, { recursive: true, force: true });
});

test('缺基线版本时拒绝拉起增量应用器', async () => {
  await assert.rejects(() => spawnDeltaApplier({
    electronExe: 'C:\\RenpyBox\\RenpyBox.exe',
    scriptPath: 'C:\\app\\update-apply.mjs',
    patchPath: 'C:\\tmp\\patch.zip',
    installDir: 'C:\\RenpyBox',
    appExe: 'C:\\RenpyBox\\RenpyBox.exe',
    pid: 42,
    tempDir: os.tmpdir(),
    copyFile: async () => {},
    spawn: () => { throw new Error('不应拉起'); },
  }), /基线版本/);
});

test('有增量包时优先下载，失败后自动改下完整安装包', async () => {
  const downloads = [];
  const updater = createDesktopUpdater({
    packaged: true,
    version: '0.9.1',
    tempDir: path.join('tmp', 'renpybox-update'),
    log: Object.assign(() => {}, { error() {} }),
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (url, destination) => {
      downloads.push(url);
      if (url.includes('.delta.zip')) throw Object.assign(new Error('增量包中断'), { kind: 'download' });
      return { path: destination, size: 1, total: 1 };
    },
  });
  const offered = await updater.check();
  assert.equal(offered.deltaAssetName.toLowerCase(), 'renpybox-0.9.2-from-0.9.1-x64.delta.zip');
  assert.equal(offered.assetName, 'RenpyBox-0.9.2-x64.exe');
  const done = await updater.download();
  assert.equal(done.status, 'downloaded');
  assert.equal(done.mode, 'full');
  assert.equal(downloads.length, 2);
  assert.match(downloads[0], /delta\.zip/);
  assert.match(done.filePath, /RenpyBox-0\.9\.2-x64\.exe$/);
});

test('跨版本升级（0.9.0 → 0.9.2）不选增量包，直接下全量', async () => {
  const downloads = [];
  const updater = createDesktopUpdater({
    packaged: true,
    version: '0.9.0',
    tempDir: path.join('tmp', 'renpybox-update'),
    log: Object.assign(() => {}, { error() {} }),
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (url, destination) => {
      downloads.push(url);
      return { path: destination, size: 1, total: 1 };
    },
  });
  const offered = await updater.check();
  assert.equal(offered.status, 'available');
  assert.equal(offered.deltaAssetUrl, '', '0.9.0 没有对应基线的增量包');
  const done = await updater.download();
  assert.equal(done.mode, 'full');
  assert.equal(downloads.length, 1);
  assert.match(downloads[0], /RenpyBox-0\.9\.2-x64\.exe$/);
});

test('增量安装拉起应用器而不是 NSIS，失败后退回可下载的完整包', async () => {
  const launches = [];
  const spawned = [];
  const quits = [];
  let recoveries = 0;
  const updater = createDesktopUpdater({
    packaged: true,
    version: '0.9.1',
    tempDir: path.join('tmp', 'renpybox-update'),
    installDir: 'D:\\Games\\RenpyBox',
    electronExe: 'D:\\Games\\RenpyBox\\RenpyBox.exe',
    deltaScriptPath: 'D:\\app\\update-apply.mjs',
    log: Object.assign(() => {}, { error() {} }),
    quit: () => quits.push(true),
    afterInstallFailure: async () => { recoveries += 1; },
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (_url, destination) => ({ path: destination, size: 1, total: 1 }),
    launchInstaller: async filePath => { launches.push(filePath); },
    spawnDeltaApplier: async options => { spawned.push(options); },
  });
  await updater.check();
  const downloaded = await updater.download();
  assert.equal(downloaded.mode, 'delta');
  await updater.install();
  assert.equal(launches.length, 0);
  assert.equal(quits.length, 1);
  assert.equal(spawned[0].patchPath, downloaded.filePath);
  assert.equal(spawned[0].installDir, 'D:\\Games\\RenpyBox');
  assert.equal(spawned[0].baseVersion, '0.9.1');
  assert.equal(spawned[0].relaunch, true);
  assert.equal(spawned[0].pid, process.pid);

  const broken = createDesktopUpdater({
    packaged: true,
    version: '0.9.1',
    tempDir: path.join('tmp', 'renpybox-update'),
    log: Object.assign(() => {}, { error() {} }),
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (_url, destination) => ({ path: destination, size: 1, total: 1 }),
    launchInstaller: async () => { throw new Error('不应启动 NSIS'); },
    spawnDeltaApplier: async () => { throw Object.assign(new Error('复制失败'), { kind: 'install' }); },
  });
  await broken.check();
  await broken.download();
  const state = await broken.install();
  assert.equal(state.status, 'available');
  assert.equal(state.mode, '');
  assert.equal(state.deltaAssetUrl, '');
  assert.equal(state.error, '增量更新失败，将回退到完整安装包');
  assert.equal(recoveries, 0);
  const again = await broken.download();
  assert.equal(again.mode, 'full');
});

test('上次增量应用失败过时，同一版本改走全量并提示原因', async () => {
  const downloads = [];
  const updater = createDesktopUpdater({
    packaged: true,
    version: '0.9.1',
    tempDir: path.join('tmp', 'renpybox-update'),
    installDir: 'D:\\Games\\RenpyBox',
    log: Object.assign(() => {}, { error() {} }),
    readApplyError: async () => ({ version: '0.9.2', error: 'HASH_MISMATCH: resources/app.asar' }),
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (url, destination) => {
      downloads.push(url);
      return { path: destination, size: 1, total: 1 };
    },
  });
  const offered = await updater.check();
  assert.equal(offered.status, 'available');
  assert.equal(offered.deltaAssetUrl, '', '失败过的版本不再给增量包');
  assert.match(offered.error, /上次增量更新失败/);
  assert.match(offered.error, /HASH_MISMATCH/);
  const done = await updater.download();
  assert.equal(done.mode, 'full');
  assert.equal(downloads.length, 1);
});

test('失败记录属于别的版本时不影响这次仍用增量包', async () => {
  const updater = createDesktopUpdater({
    packaged: true,
    version: '0.9.1',
    tempDir: path.join('tmp', 'renpybox-update'),
    log: Object.assign(() => {}, { error() {} }),
    readApplyError: async () => ({ version: '0.9.0', error: '旧版本失败' }),
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (url, destination) => ({ path: destination, size: 1, total: 1 }),
  });
  const offered = await updater.check();
  assert.equal(offered.error, '');
  assert.match(offered.deltaAssetUrl, /delta\.zip$/);
});

test('读不到失败记录时照常检查更新', async () => {
  const updater = createDesktopUpdater({
    packaged: true,
    version: '0.9.1',
    tempDir: path.join('tmp', 'renpybox-update'),
    log: Object.assign(() => {}, { error() {} }),
    readApplyError: async () => { throw new Error('权限不足'); },
    requestJson: async () => [release('0.9.2', [installer('0.9.2'), delta('0.9.2', '0.9.1')])],
    downloadFile: async (url, destination) => ({ path: destination, size: 1, total: 1 }),
  });
  const offered = await updater.check();
  assert.equal(offered.status, 'available');
  assert.match(offered.deltaAssetUrl, /delta\.zip$/);
});

test('readApplyError 读取后删除文件，只提示一次', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'renpybox-apply-error-'));
  const { writeFile } = await import('node:fs/promises');
  await writeFile(path.join(dir, '_update_error.json'), JSON.stringify({
    version: '0.9.1', patchVersion: '0.9.2', error: 'WAIT_TIMEOUT', at: '2026-10-18T00:00:00.000Z',
  }));
  const { readApplyError } = await import('../main/updater.js');
  const first = await readApplyError(dir);
  assert.deepEqual(first, { version: '0.9.2', error: 'WAIT_TIMEOUT' });
  assert.equal(await readApplyError(dir), null, '同一条失败不能反复提示');
  assert.equal(await readApplyError(''), null);
  await rm(dir, { recursive: true, force: true });
});

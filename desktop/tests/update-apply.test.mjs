import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chmod, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { deflateRawSync } from 'node:zlib';

import {
  FORMAT_MANIFEST,
  MANIFEST_NAME,
  PATCH_META_NAME,
  applyPatchCli,
  assertPatchBase,
  commitStagedFiles,
  extractPatchFiles,
  normalizePatchPath,
  parsePatchMeta,
  resolveLaunchExe,
  verifyStagedFiles,
} from '../main/update-apply.mjs';

const sha256 = data => createHash('sha256').update(data).digest('hex');

function meta(files, deleted = [], version = '0.9.2') {
  return {
    format: 'renpybox-patch/1',
    version,
    base_version: '0.9.1',
    files,
    deleted,
    manifest: { format: FORMAT_MANIFEST, version, files: {} },
  };
}

async function withTempDir(run) {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'renpybox-apply-'));
  try {
    return await run(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

/** 最小 zip：method 0 存储，method 8 deflate。不调用系统 zip。 */
function buildZip(entries) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const entry of entries) {
    const name = Buffer.from(entry.name);
    const data = Buffer.isBuffer(entry.data) ? entry.data : Buffer.from(entry.data);
    const method = entry.method ?? 0;
    const payload = method === 8 ? deflateRawSync(data) : data;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(20, 6);
    local.writeUInt16LE(method, 10);
    local.writeUInt32LE(createHash('sha256').update(data).digest().readUInt32LE(0), 14);
    local.writeUInt32LE(payload.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    const blob = Buffer.concat([local, name, payload]);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(method, 10);
    central.writeUInt32LE(payload.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(offset, 42);
    locals.push(blob);
    centrals.push(Buffer.concat([central, name]));
    offset += blob.length;
  }
  const directory = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(directory.length, 12);
  eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, eocd]);
}

test('路径校验拒绝 ..、绝对路径、反斜杠、盘符和 storage/', () => {
  assert.equal(normalizePatchPath('resources/app.asar'), 'resources/app.asar');
  for (const value of ['../x', 'foo/../../etc', '/abs', 'a\\b', 'C:/Windows/x', 'storage/config.json', 'Storage/a']) {
    assert.throws(() => normalizePatchPath(value), /非法|拒绝用户数据/);
  }
  assert.throws(() => parsePatchMeta(meta({ '_patch_meta.json': { size: 1, sha256: 'a'.repeat(64) } })), /协议文件/);
  assert.throws(() => parsePatchMeta(meta({ 'a.txt': { size: 1, sha256: 'a'.repeat(64) } }, ['_update_manifest.json'])), /协议文件/);
});

test('sha256 不符时不提交安装目录', async () => {
  await withTempDir(async dir => {
    const staging = path.join(dir, '_update_staging');
    const install = path.join(dir, 'install');
    await writeFile(path.join(dir, 'body.txt'), 'nope');
    const { mkdir } = await import('node:fs/promises');
    await mkdir(staging, { recursive: true });
    await mkdir(install, { recursive: true });
    await writeFile(path.join(staging, 'a.txt'), 'nope');
    const files = { 'a.txt': { size: 4, sha256: 'ab'.repeat(32) } };
    await assert.rejects(verifyStagedFiles(staging, files), /校验失败/);
    assert.equal(existsSync(path.join(install, 'a.txt')), false);
  });
});

test('基线版本对不上时整包拒绝，不碰安装目录', async () => {
  await withTempDir(async dir => {
    const install = path.join(dir, 'install');
    const { mkdir } = await import('node:fs/promises');
    await mkdir(install, { recursive: true });
    const parsed = parsePatchMeta(meta({ 'a.txt': { size: 1, sha256: 'a'.repeat(64) } }));
    // 传了 --base-version 且与补丁基线不同：拒绝
    await assert.rejects(
      assertPatchBase({ installDir: install, baseVersion: '0.9.0', meta: parsed }),
      /基线不匹配/,
    );
    // 安装目录里有清单且版本不一致：拒绝
    await writeFile(path.join(install, MANIFEST_NAME), JSON.stringify({ format: FORMAT_MANIFEST, version: '0.9.0', files: {} }));
    await assert.rejects(
      assertPatchBase({ installDir: install, baseVersion: '', meta: parsed }),
      /已装版本 0\.9\.0/,
    );
    // 清单与补丁基线一致，或安装目录没有清单（0.9.x 老安装包）：放行
    await writeFile(path.join(install, MANIFEST_NAME), JSON.stringify({ format: FORMAT_MANIFEST, version: '0.9.1', files: {} }));
    await assertPatchBase({ installDir: install, baseVersion: '0.9.1', meta: parsed });
    await rm(path.join(install, MANIFEST_NAME), { force: true });
    await assertPatchBase({ installDir: install, baseVersion: '0.9.1', meta: parsed });
    assert.equal(existsSync(path.join(install, 'a.txt')), false);
  });
});

test('commit 会写 .new 再覆盖，并删除 deleted、写出清单', async () => {
  await withTempDir(async dir => {
    const staging = path.join(dir, 'staging');
    const install = path.join(dir, 'install');
    const { mkdir } = await import('node:fs/promises');
    await mkdir(path.join(staging, 'resources'), { recursive: true });
    await mkdir(install, { recursive: true });
    const body = Buffer.from('hello-delta');
    await writeFile(path.join(staging, 'resources', 'app.txt'), body);
    await writeFile(path.join(install, 'old.txt'), 'gone');
    await writeFile(path.join(install, 'resources-keep.txt'), 'keep');
    const target = path.join(install, 'resources', 'app.txt');
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, 'old');
    await chmod(target, 0o444);
    const files = { 'resources/app.txt': { size: body.length, sha256: sha256(body) } };
    await verifyStagedFiles(staging, files);
    const copies = [];
    const manifest = { format: FORMAT_MANIFEST, version: '0.9.2', files: {} };
    await commitStagedFiles({
      installDir: install,
      stagingDir: staging,
      files,
      deleted: ['old.txt'],
      manifest,
      copyFile: async (from, to) => {
        copies.push(to);
        const { copyFile } = await import('node:fs/promises');
        await copyFile(from, to);
      },
    });
    assert.ok(copies.some(item => item.endsWith(`${path.sep}app.txt.new`) || item.endsWith('app.txt.new')));
    assert.equal(await readFile(target, 'utf8'), 'hello-delta');
    assert.equal(existsSync(`${target}.new`), false);
    assert.equal(existsSync(path.join(install, 'old.txt')), false);
    assert.equal(await readFile(path.join(install, 'resources-keep.txt'), 'utf8'), 'keep');
    assert.equal(JSON.parse(await readFile(path.join(install, MANIFEST_NAME), 'utf8')).version, '0.9.2');
  });
});

test('重启时按安装目录实际内容选主程序，主程序改名后也能启动', async () => {
  await withTempDir(async dir => {
    const install = path.join(dir, 'install');
    const { mkdir } = await import('node:fs/promises');
    await mkdir(path.join(install, 'resources'), { recursive: true });
    // 0.9.1 装的是 "RenpyBox New UI.exe"；增量包会删掉它并新增 RenpyBox.exe
    const legacy = path.join(install, 'RenpyBox New UI.exe');
    await writeFile(legacy, 'old');
    // 更新前路径仍存在时优先用它
    assert.equal(await resolveLaunchExe(install, legacy, ''), legacy);

    await writeFile(path.join(install, 'RenpyBox.exe'), 'new');
    await rm(legacy, { force: true });
    // 旧路径没了，必须发现新名字，而不是启动一个不存在的文件
    assert.equal(await resolveLaunchExe(install, legacy, ''), path.join(install, 'RenpyBox.exe'));
    // 清单里的安装根 exe 优先于目录扫描
    await writeFile(path.join(install, MANIFEST_NAME), JSON.stringify({
      format: FORMAT_MANIFEST, version: '0.9.2', files: { 'RenpyBox.exe': { size: 3, sha256: 'a'.repeat(64) } },
    }));
    assert.equal(await resolveLaunchExe(install, '', '0.9.2'), path.join(install, 'RenpyBox.exe'));
    // 目录里一个 exe 都没有时返回空串，由调用方记日志
    await rm(path.join(install, 'RenpyBox.exe'), { force: true });
    assert.equal(await resolveLaunchExe(install, legacy, ''), '');
  });
});

test('解压只取出 files 中的成员，坏路径和错误摘要都不会提交', async () => {
  await withTempDir(async dir => {
    const body = Buffer.from('payload');
    const digest = sha256(body);
    const parsed = parsePatchMeta(meta({
      'resources/app.txt': { size: body.length, sha256: digest },
    }, ['old.txt']));
    const zipPath = path.join(dir, 'patch.zip');
    await writeFile(zipPath, buildZip([
      { name: PATCH_META_NAME, data: JSON.stringify(parsed) },
      { name: 'resources/app.txt', data: body, method: 8 },
      { name: 'ignored.txt', data: 'skip' },
    ]));
    const install = path.join(dir, 'install');
    const { mkdir } = await import('node:fs/promises');
    await mkdir(install, { recursive: true });
    await writeFile(path.join(install, 'old.txt'), 'bye');
    const child = spawn(process.execPath, ['-e', 'process.exit(0)'], { stdio: 'ignore' });
    await once(child, 'exit');
    const code = await applyPatchCli([
      '--patch', zipPath,
      '--install-dir', install,
      '--app-exe', process.execPath,
      '--pid', String(child.pid),
      '--base-version', '0.9.1',
      '--relaunch', '0',
    ]);
    assert.equal(code, 0);
    assert.equal(await readFile(path.join(install, 'resources', 'app.txt'), 'utf8'), 'payload');
    assert.equal(existsSync(path.join(install, 'ignored.txt')), false);
    assert.equal(existsSync(path.join(install, 'old.txt')), false);
    assert.equal(existsSync(path.join(install, '_update_staging')), false);
    assert.match(await readFile(path.join(install, '_update_apply.log'), 'utf8'), /增量更新完成/);

    const badZip = path.join(dir, 'bad.zip');
    await writeFile(badZip, buildZip([
      { name: PATCH_META_NAME, data: JSON.stringify(parsed) },
      { name: 'resources/app.txt', data: Buffer.from('tampered'), method: 8 },
    ]));
    const badInstall = path.join(dir, 'bad-install');
    await mkdir(badInstall, { recursive: true });
    const badCode = await applyPatchCli([
      '--patch', badZip, '--install-dir', badInstall, '--app-exe', process.execPath,
      '--pid', String(child.pid), '--relaunch', '0',
    ]);
    assert.equal(badCode, 1);
    assert.equal(existsSync(path.join(badInstall, 'resources', 'app.txt')), false);
    const errorFile = JSON.parse(await readFile(path.join(badInstall, '_update_error.json'), 'utf8'));
    assert.equal(errorFile.patchVersion, '0.9.2');
    assert.match(errorFile.error, /校验失败/);

    const evil = path.join(dir, 'evil.zip');
    await writeFile(evil, buildZip([
      { name: PATCH_META_NAME, data: '{}' },
      { name: 'storage/secret.txt', data: 'no' },
    ]));
    await assert.rejects(extractPatchFiles(evil, path.join(dir, 'stage'), {}), /拒绝用户数据|非法/);
  });
});

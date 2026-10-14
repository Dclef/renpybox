import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, readdir, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { downloadInstaller } from '../main/updater-download.js';

const PAYLOAD = Buffer.from('renpybox-installer-payload');
const DIGEST = createHash('sha256').update(PAYLOAD).digest('hex');
const EXPECTED_DIGEST = `sha256:${DIGEST}`;
const EXPECTED_SIZE = PAYLOAD.length;

const respond = (body, { status = 200, headers } = {}) => new Response(body, {
  status,
  headers: headers ?? { 'content-length': String(EXPECTED_SIZE) },
});

async function workdir(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'renpybox-download-'));
  try {
    return await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test('缺少发布校验值或大小无效时直接拒绝，不产生任何文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: 'md5:whatever',
        fetchImpl: async () => { throw new Error('不应发起下载'); },
      }),
      /SHA-256/,
    );
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: 0,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => { throw new Error('不应发起下载'); },
      }),
      /大小无效/,
    );
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('下载内容大小与发布资产不一致时丢弃临时文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => respond(PAYLOAD, { headers: { 'content-length': String(EXPECTED_SIZE + 1) } }),
      }),
      /长度/,
    );
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE + 1,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => respond(PAYLOAD, { headers: {} }),
      }),
      /文件大小与发布资产不一致/,
    );
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('SHA-256 不匹配时丢弃安装包', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: `sha256:${'0'.repeat(64)}`,
        fetchImpl: async () => respond(PAYLOAD),
      }),
      /校验失败/,
    );
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('校验通过后才发布安装包，并报告进度', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'nested', 'installer.exe');
    const progress = [];
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      onProgress: event => progress.push(event),
      fetchImpl: async () => respond(PAYLOAD),
    });
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
    assert.deepEqual(progress, [{ received: EXPECTED_SIZE, total: EXPECTED_SIZE }]);
    assert.deepEqual(await readdir(path.dirname(destination)), ['installer.exe']);
  });
});

test('HTTP 失败与取消都不留下文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => respond('rate limited', { status: 403, headers: {} }),
      }),
      /GitHub 返回 403/,
    );
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        signal: controller.signal,
        fetchImpl: async () => { throw new Error('取消后不应发起下载'); },
      }),
      error => error?.name === 'AbortError',
    );
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(directory), []);
  });
});
